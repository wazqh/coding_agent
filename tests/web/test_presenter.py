from __future__ import annotations

from coding_agent.events import AgentEvent, AgentState, EventKind
from coding_agent.web.presenter import AgentEventPresenter
from coding_agent.web.protocol import ViewEventType

SESSION_ID = "a" * 24
TURN_ID = "turn-1"


def _event(kind: EventKind, data: dict[str, object], state: AgentState | None = None) -> AgentEvent:
    return AgentEvent(
        kind=kind,
        session_id=SESSION_ID,
        turn_id=TURN_ID,
        state=state,
        data=data,
    )


def test_presenter_pairs_tool_results_and_groups_routine_activity() -> None:
    presenter = AgentEventPresenter()

    read_call = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {"id": "call-1", "name": "read_file", "arguments": {"path": "src/a.py"}},
        )
    )[0]
    search_call = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {"id": "call-2", "name": "search_text", "arguments": {"query": "token"}},
        )
    )[0]
    read_result = presenter.present(
        _event(
            EventKind.TOOL_RESULT,
            {
                "id": "call-1",
                "name": "read_file",
                "result": {
                    "ok": True,
                    "code": "OK",
                    "summary": "read 20 lines",
                    "data": {"content": "secret detail remains expandable"},
                },
            },
        )
    )[0]
    search_result = presenter.present(
        _event(
            EventKind.TOOL_RESULT,
            {
                "id": "call-2",
                "name": "search_text",
                "result": {
                    "ok": True,
                    "code": "OK",
                    "summary": "found 3 matches",
                    "data": {},
                },
            },
        )
    )[0]

    assert read_call.type is ViewEventType.ACTIVITY_UPSERT
    assert read_call.data["activity_id"] == search_call.data["activity_id"]
    assert search_call.data["count"] == 2
    assert search_call.data["detail"]["steps"] == [
        {
            "name": "read_file",
            "subject": "读取 src/a.py",
            "status": "running",
            "summary": "",
        },
        {
            "name": "search_text",
            "subject": "搜索 token",
            "status": "running",
            "summary": "",
        },
    ]
    assert read_result.data["status"] == "running"
    assert read_result.data["detail"]["steps"][0] == {
        "name": "read_file",
        "subject": "读取 src/a.py",
        "status": "completed",
        "summary": "read 20 lines",
    }
    assert read_result.data["detail"]["raw"]["data"]["content"] == (
        "secret detail remains expandable"
    )
    assert search_result.data["status"] == "completed"
    assert search_result.data["summary"] == "found 3 matches"
    assert search_result.data["detail"]["steps"][1]["summary"] == "found 3 matches"


def test_presenter_separates_command_validation_from_routine_activity() -> None:
    presenter = AgentEventPresenter()
    call = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {"id": "call-test", "name": "run_command", "arguments": {"command": "pytest -q"}},
        )
    )[0]
    result = presenter.present(
        _event(
            EventKind.TOOL_RESULT,
            {
                "id": "call-test",
                "name": "run_command",
                "result": {"ok": True, "summary": "24 passed", "data": {"exit_code": 0}},
            },
        )
    )[0]

    assert call.data["kind"] == "validation"
    assert result.data["kind"] == "validation"
    assert result.data["summary"] == "24 passed"


def test_presenter_keeps_ordinary_shell_commands_as_commands() -> None:
    presenter = AgentEventPresenter()
    call = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {
                "id": "call-command",
                "name": "run_command",
                "arguments": {"command": "git check-ignore -v test/example.py"},
            },
        )
    )[0]
    result = presenter.present(
        _event(
            EventKind.TOOL_RESULT,
            {
                "id": "call-command",
                "name": "run_command",
                "result": {"ok": True, "summary": "ignored by test/", "data": {}},
            },
        )
    )[0]

    assert call.data["kind"] == "command"
    assert call.data["title"] == "运行命令"
    assert result.data["kind"] == "command"
    assert result.data["detail"]["data"]["command"] == "git check-ignore -v test/example.py"


def test_presenter_labels_the_runtime_edit_file_tool_as_a_file_change() -> None:
    presenter = AgentEventPresenter()
    call = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {
                "id": "call-edit",
                "name": "edit_file",
                "arguments": {"path": "src/app.py", "old_text": "a", "new_text": "b"},
            },
        )
    )[0]

    assert call.data["kind"] == "file_change"
    assert call.data["title"] == "修改文件"
    assert call.data["summary"] == "src/app.py"


def test_presenter_publishes_a_successful_file_change_immediately() -> None:
    presenter = AgentEventPresenter()
    events = presenter.present(
        _event(
            EventKind.TOOL_RESULT,
            {
                "id": "call-write",
                "name": "write_file",
                "result": {
                    "ok": True,
                    "code": "OK",
                    "summary": "created src/new.py",
                    "data": {
                        "change_id": "a" * 32,
                        "change_kind": "created",
                        "path": "src/new.py",
                        "sha256": "b" * 64,
                        "diff": (
                            "--- a/src/new.py\n+++ b/src/new.py\n@@ -0,0 +1 @@\n+print('new')\n"
                        ),
                    },
                },
            },
        )
    )

    assert [event.type for event in events] == [
        ViewEventType.ACTIVITY_UPSERT,
        ViewEventType.CHANGE_RECORDED,
    ]
    assert events[1].data == {
        "id": "a" * 32,
        "path": "src/new.py",
        "kind": "created",
        "additions": 1,
        "deletions": 0,
        "diff": "--- a/src/new.py\n+++ b/src/new.py\n@@ -0,0 +1 @@\n+print('new')\n",
        "reversible": True,
    }


def test_presenter_uses_plan_event_without_duplicate_update_plan_activity() -> None:
    presenter = AgentEventPresenter()

    assert (
        presenter.present(
            _event(
                EventKind.TOOL_CALL,
                {"id": "call-plan", "name": "update_plan", "arguments": {"plan": []}},
            )
        )
        == []
    )
    assert (
        presenter.present(
            _event(
                EventKind.TOOL_RESULT,
                {
                    "id": "call-plan",
                    "name": "update_plan",
                    "result": {"ok": True, "summary": "plan updated with 5 steps"},
                },
            )
        )
        == []
    )

    plan = presenter.present(
        _event(EventKind.PLAN, {"plan": [{"step": "验证", "status": "in_progress"}]})
    )
    assert [item.type for item in plan] == [ViewEventType.PLAN_UPDATED]


def test_presenter_maps_stream_plan_approval_usage_error_and_completion() -> None:
    presenter = AgentEventPresenter()
    source = [
        _event(EventKind.TEXT, {"delta": "Hello"}),
        _event(EventKind.PLAN, {"plan": [{"step": "test", "status": "in_progress"}]}),
        _event(
            EventKind.APPROVAL,
            {
                "request": {
                    "action": "run_command",
                    "subject": "pytest -q",
                    "summary": "run tests",
                    "diff": None,
                }
            },
            AgentState.AWAITING_APPROVAL,
        ),
        _event(EventKind.APPROVAL, {"decision": "deny", "subject": "pytest -q"}),
        _event(EventKind.USAGE, {"prompt_tokens": 50, "completion_tokens": 10}),
        _event(EventKind.ERROR, {"message": "model failed"}),
        _event(
            EventKind.DONE,
            {"reason": "assistant completed", "exit_code": 0, "tool_steps": 1},
            AgentState.COMPLETED,
        ),
    ]

    presented = [event for item in source for event in presenter.present(item)]

    assert [item.type for item in presented] == [
        ViewEventType.MESSAGE_DELTA,
        ViewEventType.PLAN_UPDATED,
        ViewEventType.APPROVAL_REQUESTED,
        ViewEventType.APPROVAL_RESOLVED,
        ViewEventType.CONTEXT_UPDATED,
        ViewEventType.ERROR,
        ViewEventType.TURN_FINISHED,
    ]
    assert [item.seq for item in presented] == list(range(1, 8))
    assert presented[-1].data["status"] == "completed"
    assert presented[4].data == {
        "prompt_tokens": 50,
        "completion_tokens": 10,
        "total_tokens": 60,
    }


def test_presenter_keeps_live_lifecycle_progress_for_the_desktop_timeline() -> None:
    presenter = AgentEventPresenter()

    progress = presenter.present(
        _event(
            EventKind.STATE,
            {"step": 3, "tool": "read_file"},
            AgentState.EXECUTING,
        )
    )

    assert len(progress) == 1
    assert progress[0].type is ViewEventType.TURN_PROGRESS
    assert progress[0].data == {
        "status": "executing",
        "step": 3,
        "tool": "read_file",
    }


def test_history_uses_final_messages_and_ignores_text_deltas() -> None:
    records = [
        {
            "type": "message",
            "data": {"role": "user", "content": "hello"},
            "timestamp": "2026-08-29T00:00:00Z",
        },
        {
            "type": "event",
            "data": _event(EventKind.TEXT, {"delta": "duplicate"}).model_dump(mode="json"),
            "timestamp": "2026-08-29T00:00:01Z",
        },
        {
            "type": "message",
            "data": {"role": "assistant", "content": "final answer"},
            "timestamp": "2026-08-29T00:00:02Z",
        },
    ]

    history = AgentEventPresenter().present_history(SESSION_ID, records)

    assert [(item.data["role"], item.data["content"]) for item in history] == [
        ("user", "hello"),
        ("assistant", "final answer"),
    ]
    assert all(item.type is ViewEventType.MESSAGE_FINAL for item in history)
