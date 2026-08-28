from __future__ import annotations

from collections.abc import Callable, Iterator
from threading import Event
from typing import Any

import pytest
from conftest import FakeModel

from coding_agent.config import Settings
from coding_agent.context import estimate_request_tokens
from coding_agent.controller import AgentController
from coding_agent.events import AgentState, EventKind, ModelStreamEvent, ToolCall
from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.session import SessionError, SessionStore
from coding_agent.tools.registry import default_registry


def text_response(value: str) -> list[ModelStreamEvent]:
    return [
        ModelStreamEvent(type="text_delta", text=value),
        ModelStreamEvent(type="done", finish_reason="stop"),
    ]


def tool_response(call: ToolCall) -> list[ModelStreamEvent]:
    return [
        ModelStreamEvent(type="tool_calls", tool_calls=[call]),
        ModelStreamEvent(type="done", finish_reason="tool_calls"),
    ]


def make_controller(
    settings: Settings,
    model: FakeModel,
    *,
    approval: ApprovalPolicy | None = None,
    session_id: str | None = None,
    events: list | None = None,
    monotonic: Callable[[], float] | None = None,
) -> AgentController:
    sessions = SessionStore(settings.data_dir)
    return AgentController(
        settings=settings,
        model=model,  # type: ignore[arg-type]
        tools=default_registry(),
        sessions=sessions,
        approval=approval or ApprovalPolicy("auto"),
        session_id=session_id,
        event_sink=events.append if events is not None else None,
        **({"monotonic": monotonic} if monotonic is not None else {}),
    )


def test_agent_loop_tool_observation_then_completion(settings: Settings) -> None:
    (settings.cwd / "a.py").write_text("print('a')\n", encoding="utf-8")
    model = FakeModel(
        [
            tool_response(
                ToolCall(
                    id="call1",
                    name="list_files",
                    arguments={"path": ".", "pattern": "*.py"},
                    thought_signature="sig-1",
                )
            ),
            text_response("All files checked."),
        ]
    )
    events: list = []
    controller = make_controller(settings, model, events=events)
    result = controller.run_turn("inspect the project")
    assert result.status is AgentState.COMPLETED
    assert result.tool_steps == 1
    assert any(event.kind is EventKind.TOOL_RESULT for event in events)
    second_request = model.requests[1][0]
    assert any(message.get("role") == "tool" for message in second_request)
    assistant = next(
        message
        for message in second_request
        if message.get("role") == "assistant" and message.get("tool_calls")
    )
    assert assistant["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "sig-1"
    assert controller.last_context_tokens == estimate_request_tokens(*model.requests[-1])
    assert SessionStore(settings.data_dir).messages(result.session_id)


def test_loop_guard_stops_third_identical_failure(settings: Settings) -> None:
    call = ToolCall(id="same", name="does_not_exist", arguments={})
    model = FakeModel([tool_response(call), tool_response(call), tool_response(call)])
    events: list = []
    controller = make_controller(settings, model, events=events)
    result = controller.run_turn("keep trying")
    assert result.status is AgentState.FAILED
    assert result.tool_steps == 3
    assert "loop guard" in result.reason
    assert any(event.kind is EventKind.WARNING for event in events)


def test_noninteractive_approval_returns_policy_exit(settings: Settings) -> None:
    call = ToolCall(
        id="write",
        name="write_file",
        arguments={"path": "created.txt", "content": "content"},
    )
    model = FakeModel([tool_response(call)])
    controller = make_controller(
        settings,
        model,
        approval=ApprovalPolicy("prompt", interactive=False),
    )
    result = controller.run_turn("create a file")
    assert result.exit_code == 3
    assert not (settings.cwd / "created.txt").exists()


def test_model_error_empty_response_and_step_budget(settings: Settings) -> None:
    error_model = FakeModel([[ModelStreamEvent(type="error", error="offline")]])
    failed = make_controller(settings, error_model).run_turn("task")
    assert "model error" in failed.reason

    empty_model = FakeModel([[ModelStreamEvent(type="done", finish_reason="stop")]])
    empty = make_controller(settings, empty_model).run_turn("task")
    assert "neither text nor tool" in empty.reason

    settings.agent.max_steps = 1
    calls = [
        ToolCall(id="one", name="list_files", arguments={}),
        ToolCall(id="two", name="read_file", arguments={"path": "never.txt"}),
    ]
    budget_model = FakeModel(
        [
            [
                ModelStreamEvent(type="tool_calls", tool_calls=calls),
                ModelStreamEvent(type="done", finish_reason="tool_calls"),
            ]
        ]
    )
    budget = make_controller(settings, budget_model).run_turn("task")
    assert budget.reason == "tool step budget exhausted"
    skipped = SessionStore(settings.data_dir).messages(budget.session_id)[-1]
    assert "STEP_BUDGET_EXHAUSTED" in skipped["content"]


def test_resume_and_workspace_isolation(settings: Settings) -> None:
    first_model = FakeModel([text_response("first")])
    first = make_controller(settings, first_model)
    result = first.run_turn("do work")
    resumed_model = FakeModel([text_response("second")])
    resumed = make_controller(settings, resumed_model, session_id=result.session_id)
    assert any(message.get("content") == "do work" for message in resumed.conversation)
    assert resumed.run_turn("continue").status is AgentState.COMPLETED

    other_workspace = settings.cwd / "other"
    other_workspace.mkdir()
    other_settings = settings.model_copy(update={"cwd": other_workspace})
    with pytest.raises(SessionError, match="different workspace"):
        make_controller(other_settings, FakeModel([]), session_id=result.session_id)


def test_manual_compaction_keeps_transcript(settings: Settings) -> None:
    model = FakeModel([text_response(str(index)) for index in range(6)])
    controller = make_controller(settings, model)
    for index in range(6):
        controller.run_turn(f"turn {index}")
    original_records = len(SessionStore(settings.data_dir).replay(controller.session_id))
    summary = controller.manual_compact()
    assert summary
    records = SessionStore(settings.data_dir).replay(controller.session_id)
    assert len(records) > original_records
    compact_record = next(record for record in reversed(records) if record["type"] == "compact")
    assert compact_record["data"]["conversation"] == controller.conversation

    resumed = make_controller(settings, FakeModel([]), session_id=controller.session_id)
    assert resumed.conversation == controller.conversation
    assert any(
        message.get("role") == "system" and "Conversation summary" in message.get("content", "")
        for message in resumed.conversation
    )


def test_multiple_tool_calls_are_executed_in_model_order(settings: Settings) -> None:
    (settings.cwd / "a.txt").write_text("a", encoding="utf-8")
    calls = [
        ToolCall(id="first", name="list_files", arguments={"pattern": "*.txt"}),
        ToolCall(id="second", name="read_file", arguments={"path": "a.txt"}),
    ]
    model = FakeModel(
        [
            [
                ModelStreamEvent(type="tool_calls", tool_calls=calls),
                ModelStreamEvent(type="done", finish_reason="tool_calls"),
            ],
            text_response("done"),
        ]
    )
    result = make_controller(settings, model).run_turn("inspect")
    assert result.tool_steps == 2
    tool_messages = [message for message in model.requests[1][0] if message.get("role") == "tool"]
    assert [message["tool_call_id"] for message in tool_messages] == ["first", "second"]


def test_time_budget_and_keyboard_interrupt_are_persisted(settings: Settings) -> None:
    times = iter([0.0, 61.0])
    timed = make_controller(
        settings,
        FakeModel([]),
        monotonic=lambda: next(times),
    ).run_turn("slow task")
    assert timed.reason == "turn time budget exhausted"

    class InterruptModel:
        def stream(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> Iterator[ModelStreamEvent]:
            raise KeyboardInterrupt
            yield ModelStreamEvent(type="done")

    cancelled = make_controller(
        settings,
        InterruptModel(),  # type: ignore[arg-type]
    ).run_turn("cancel me")
    assert cancelled.status is AgentState.CANCELLED
    assert cancelled.exit_code == 130
    records = SessionStore(settings.data_dir).replay(cancelled.session_id)
    assert records[-1]["data"]["status"] == "cancelled"


def test_escape_cancellation_stops_before_model_call(settings: Settings) -> None:
    cancel_event = Event()
    cancel_event.set()
    model = FakeModel([text_response("must not run")])
    result = make_controller(settings, model).run_turn("cancel this", cancel_event=cancel_event)
    assert result.status is AgentState.CANCELLED
    assert result.exit_code == 130
    assert result.reason == "cancelled by Esc"
    assert model.requests == []


def test_resume_after_unanswered_turn_coalesces_provider_history(settings: Settings) -> None:
    cancel_event = Event()
    cancel_event.set()
    cancelled_controller = make_controller(settings, FakeModel([]))
    cancelled = cancelled_controller.run_turn("first request", cancel_event=cancel_event)

    model = FakeModel([text_response("continued")])
    resumed = make_controller(settings, model, session_id=cancelled.session_id)
    result = resumed.run_turn("follow-up request")

    assert result.status is AgentState.COMPLETED
    request_messages = model.requests[0][0]
    user_messages = [message for message in request_messages if message.get("role") == "user"]
    assert len(user_messages) == 1
    assert user_messages[0]["content"] == "first request\n\nfollow-up request"
    assert [message.get("role") for message in resumed.conversation[:2]] == ["user", "user"]


def test_provider_history_repairs_old_compact_boundary() -> None:
    prepared = AgentController._messages_for_model(
        [
            {"role": "system", "content": "current instructions"},
            {"role": "system", "content": "compact summary"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "orphan", "type": "function", "function": {}}],
            },
            {"role": "tool", "tool_call_id": "orphan", "content": "old result"},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": "first pending request"},
            {"role": "user", "content": "second pending request"},
        ]
    )

    assert [message["role"] for message in prepared] == ["system", "user"]
    assert prepared[0]["content"] == "current instructions\n\ncompact summary"
    assert prepared[1]["content"] == "first pending request\n\nsecond pending request"


def test_provider_history_merges_adjacent_structured_user_content() -> None:
    first = [{"type": "text", "text": "first"}]
    second = [{"type": "text", "text": "second"}]

    prepared = AgentController._messages_for_model(
        [
            {"role": "system", "content": "instructions"},
            {"role": "user", "content": first},
            {"role": "user", "content": second},
        ]
    )

    assert prepared == [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": [*first, *second]},
    ]
