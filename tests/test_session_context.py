from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.context import ContextManager, estimate_request_tokens, estimate_tokens
from coding_agent.session import SessionError, SessionStore, concise_session_title
from coding_agent.tools.base import WorkingState


def test_session_round_trip_listing_and_corruption(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "data")
    session_id = store.create({"workspace": str(tmp_path)})
    store.append_message(session_id, {"role": "user", "content": "fix dates"})
    store.append_message(session_id, {"role": "assistant", "content": "done"})
    assert len(store.messages(session_id)) == 2
    listed = store.list()[0]
    assert listed["title"] == "fix dates"
    assert listed["workspace"] == str(tmp_path)
    assert listed["model"] == ""
    with pytest.raises(SessionError):
        store.replay("../bad")
    path = store.directory / f"{session_id}.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        stream.write("not-json\n")
    with pytest.raises(SessionError, match="corrupt"):
        store.replay(session_id)


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("请帮我 修复登录页的 token 刷新问题，然后运行测试", "修复登录页的 token 刷新问题"),
        ("麻烦优化一下中文会话标题。后面还有说明", "优化一下中文会话标题"),
        ("   ", "未命名任务"),
        (
            "实现一个非常非常非常非常非常非常长的项目标题用于测试",
            "实现一个非常非常非常非常非常非常长的项目标题用…",
        ),
    ],
)
def test_concise_session_title_normalizes_task_text(task: str, expected: str) -> None:
    assert concise_session_title(task) == expected


def test_persisted_session_title_takes_precedence_over_legacy_first_message(
    tmp_path: Path,
) -> None:
    store = SessionStore(tmp_path / "data")
    session_id = store.create({"workspace": str(tmp_path)})
    store.append_message(session_id, {"role": "user", "content": "请帮我处理旧标题"})

    title = store.ensure_title(session_id, "请帮我改造会话组织，然后运行测试")
    repeated = store.ensure_title(session_id, "另一个标题不应覆盖")

    assert title == "改造会话组织"
    assert repeated == title
    assert store.list()[0]["title"] == title
    assert sum(record["type"] == "session_title" for record in store.replay(session_id)) == 1


def test_context_compaction_preserves_recent_and_summary() -> None:
    messages: list[dict[str, object]] = []
    for index in range(8):
        messages.extend(
            [
                {"role": "user", "content": f"request {index}"},
                {"role": "assistant", "content": f"answer {index}"},
            ]
        )
    working = WorkingState(
        goal="goal",
        plan=[
            {"step": "read", "status": "completed"},
            {"step": "test", "status": "in_progress"},
        ],
    )
    manager = ContextManager(context_window=20, threshold=0.7)
    assert manager.should_compact(messages)
    compacted, summary = manager.compact(messages, working)
    assert len(compacted) == 9
    assert compacted[-1] == messages[-1]
    assert "Completed changes: read" in summary
    assert "Pending work: test" in summary
    assert estimate_tokens(compacted) > 0


def test_context_compaction_handles_few_very_large_completed_turns() -> None:
    large = "decision and implementation detail " * 800
    messages: list[dict[str, object]] = [
        {"role": "user", "content": f"first request {large}"},
        {"role": "assistant", "content": f"first result {large}"},
        {"role": "user", "content": f"second request {large}"},
        {"role": "assistant", "content": f"second result {large}"},
        {"role": "user", "content": "latest request"},
        {"role": "assistant", "content": "latest result"},
    ]

    compacted, summary = ContextManager(context_window=128).compact(
        messages, WorkingState(goal="latest request")
    )

    assert summary
    assert len(compacted) < len(messages)
    assert compacted[-2:] == messages[-2:]
    assert "first request" in summary


def test_context_compaction_does_not_compact_a_single_completed_turn() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "request " + ("x" * 10_000)},
        {"role": "assistant", "content": "answer " + ("y" * 10_000)},
    ]

    compacted, summary = ContextManager(context_window=128).compact(
        messages, WorkingState(goal="request")
    )

    assert compacted == messages
    assert summary == ""


def test_context_compaction_never_splits_active_tool_turn() -> None:
    signature_call = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-0",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
                "extra_content": {"google": {"thought_signature": "sig-1"}},
            }
        ],
    }
    messages: list[dict[str, object]] = []
    for index in range(5):
        messages.extend(
            [
                {"role": "user", "content": f"old request {index}"},
                {"role": "assistant", "content": f"old answer {index}"},
            ]
        )
    messages.extend([{"role": "user", "content": "active request"}, signature_call])
    for index in range(5):
        messages.append({"role": "tool", "tool_call_id": f"call-{index}", "content": "result"})
        if index < 4:
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call-{index + 1}",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"},
                        }
                    ],
                }
            )

    compacted, summary = ContextManager(context_window=20).compact(
        messages, WorkingState(goal="active request")
    )

    assert summary
    assert {"role": "user", "content": "active request"} in compacted
    assert signature_call in compacted
    assert next(message for message in compacted if message["role"] != "system")["role"] == "user"


def test_repeated_compaction_keeps_one_summary_and_full_turn_boundaries() -> None:
    messages: list[dict[str, object]] = [
        {"role": "system", "content": "Conversation summary\nGoal: original goal"},
        {"role": "system", "content": "stale duplicate summary"},
    ]
    for index in range(7):
        messages.extend(
            [
                {"role": "user", "content": f"request {index}"},
                {"role": "assistant", "content": f"answer {index}"},
            ]
        )

    compacted, summary = ContextManager(context_window=20).compact(
        messages, WorkingState(goal="latest goal")
    )

    assert summary
    assert "Goal: original goal" in summary
    assert sum(message["role"] == "system" for message in compacted) == 1
    assert compacted[1] == {"role": "user", "content": "request 3"}
    assert estimate_request_tokens(compacted, [{"type": "function", "name": "demo"}]) > (
        estimate_tokens(compacted)
    )
