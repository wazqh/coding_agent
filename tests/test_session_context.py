from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.context import ContextManager, estimate_tokens
from coding_agent.session import SessionError, SessionStore
from coding_agent.tools.base import WorkingState


def test_session_round_trip_listing_and_corruption(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "data")
    session_id = store.create({"workspace": str(tmp_path)})
    store.append_message(session_id, {"role": "user", "content": "fix dates"})
    store.append_message(session_id, {"role": "assistant", "content": "done"})
    assert len(store.messages(session_id)) == 2
    assert store.list()[0]["title"] == "fix dates"
    with pytest.raises(SessionError):
        store.replay("../bad")
    path = store.directory / f"{session_id}.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        stream.write("not-json\n")
    with pytest.raises(SessionError, match="corrupt"):
        store.replay(session_id)


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


def test_context_compaction_never_splits_active_tool_turn() -> None:
    signature_call = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
                "extra_content": {"google": {"thought_signature": "sig-1"}},
            }
        ],
    }
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "old request"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "active request"},
        signature_call,
    ]
    for index in range(5):
        messages.extend(
            [
                {"role": "tool", "tool_call_id": f"call-{index}", "content": "result"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call-{index + 2}",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"},
                        }
                    ],
                },
            ]
        )

    compacted, summary = ContextManager(context_window=20).compact(
        messages, WorkingState(goal="active request")
    )

    assert summary
    assert {"role": "user", "content": "active request"} in compacted
    assert signature_call in compacted
