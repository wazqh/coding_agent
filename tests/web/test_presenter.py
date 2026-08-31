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


def test_presenter_groups_symbol_navigation_as_read_only_workspace_activity() -> None:
    presenter = AgentEventPresenter()

    outline = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {"id": "symbols", "name": "list_symbols", "arguments": {"path": "src/app.py"}},
        )
    )[0]
    definition = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {
                "id": "definition",
                "name": "find_definition",
                "arguments": {"symbol": "main", "path": "src"},
            },
        )
    )[0]

    assert outline.data["kind"] == "workspace_check"
    assert outline.data["summary"] == "索引 src/app.py 的符号"
    assert definition.data["activity_id"] == outline.data["activity_id"]
    assert definition.data["summary"] == "查找 main 的定义"


def test_presenter_keeps_agent_initiated_test_commands_as_ordinary_commands() -> None:
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

    assert call.data["kind"] == "command"
    assert result.data["kind"] == "command"
    assert result.data["summary"] == "24 passed"


def test_presenter_marks_configured_verification_commands_as_validation() -> None:
    presenter = AgentEventPresenter()
    call = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {
                "id": "verification-1",
                "name": "run_command",
                "arguments": {"command": "scripts/check-project.ps1"},
                "verification": True,
            },
        )
    )[0]
    result = presenter.present(
        _event(
            EventKind.TOOL_RESULT,
            {
                "id": "verification-1",
                "name": "run_command",
                "verification": True,
                "result": {"ok": True, "summary": "checks passed", "data": {}},
            },
        )
    )[0]

    assert call.data["kind"] == "validation"
    assert call.data["title"] == "运行验证"
    assert result.data["kind"] == "validation"


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


def test_presenter_labels_hard_blocked_commands_as_safety_events() -> None:
    presenter = AgentEventPresenter()
    presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {
                "id": "call-blocked",
                "name": "run_command",
                "arguments": {"command": "git clean -fd"},
            },
        )
    )
    result = presenter.present(
        _event(
            EventKind.TOOL_RESULT,
            {
                "id": "call-blocked",
                "name": "run_command",
                "result": {
                    "ok": False,
                    "code": "DANGEROUS_COMMAND",
                    "summary": "command matches a destructive safety rule",
                    "data": {
                        "hard_blocked": True,
                        "risk_label": "强制清理 Git 工作区",
                    },
                },
            },
        )
    )[0]

    assert result.data["title"] == "已阻止高风险命令"
    assert result.data["summary"] == "强制清理 Git 工作区"


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


def test_presenter_labels_verification_registration_as_a_formal_rule() -> None:
    presenter = AgentEventPresenter()

    call = presenter.present(
        _event(
            EventKind.TOOL_CALL,
            {
                "id": "register-1",
                "name": "register_verification",
                "arguments": {
                    "label": "Algorithm tests",
                    "command": "python -m pytest tests -q",
                    "cwd": "algorithm_practice",
                },
            },
        )
    )[0]

    assert call.data["kind"] == "verification_setup"
    assert call.data["title"] == "登记验证规则"
    assert call.data["summary"] == "Algorithm tests · algorithm_practice"


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
        "review_status": "pending",
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


def test_presenter_turns_tool_bearing_text_into_a_progress_note() -> None:
    presented = AgentEventPresenter().present(
        _event(
            EventKind.TEXT,
            {"delta": "I will inspect the relevant files first.", "phase": "progress"},
        )
    )

    assert len(presented) == 1
    assert presented[0].type is ViewEventType.ACTIVITY_UPSERT
    assert presented[0].data["kind"] == "agent_note"
    assert presented[0].data["title"] == "Agent 说明"
    assert presented[0].data["summary"] == "I will inspect the relevant files first."
    assert presented[0].data["detail"] == {"markdown": "I will inspect the relevant files first."}


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


def test_history_restores_durable_verification_results_with_exact_status() -> None:
    records = [
        {
            "type": "verification_result",
            "data": {
                "turn_id": TURN_ID,
                "status": "timed_out",
                "command_count": 1,
                "check_id": "focused-tests",
                "command": "python -m pytest tests/test_one.py -q",
                "cwd": ".",
                "target_paths": ["src/one.py"],
                "summary": "verification timed out",
                "execution_ms": 120000,
                "manual": True,
            },
        }
    ]

    history = AgentEventPresenter().present_history(SESSION_ID, records)

    assert len(history) == 1
    assert history[0].type is ViewEventType.VERIFICATION_FINISHED
    assert history[0].turn_id == TURN_ID
    assert history[0].data["status"] == "timed_out"
    assert history[0].data["target_paths"] == ["src/one.py"]


def test_live_automatic_verification_result_is_presented_semantically() -> None:
    event = _event(
        EventKind.VERIFICATION,
        {
            "turn_id": TURN_ID,
            "status": "not_configured",
            "command_count": 0,
            "summary": "No verification rule covers the changed files.",
            "target_paths": ["examples/demo.py"],
            "manual": False,
        },
    )

    presented = AgentEventPresenter().present(event)

    assert len(presented) == 1
    assert presented[0].type is ViewEventType.VERIFICATION_FINISHED
    assert presented[0].data["status"] == "not_configured"
    assert presented[0].data["manual"] is False


def test_history_does_not_present_tool_bearing_assistant_content_as_a_final_answer() -> None:
    records = [
        {
            "type": "message",
            "data": {"role": "user", "content": "inspect the project"},
        },
        {
            "type": "message",
            "data": {
                "role": "assistant",
                "content": "I will inspect the project first.",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"README.md"}',
                        },
                    }
                ],
            },
        },
        {
            "type": "event",
            "data": _event(
                EventKind.TOOL_CALL,
                {
                    "id": "call-1",
                    "name": "read_file",
                    "arguments": {"path": "README.md"},
                },
            ).model_dump(mode="json"),
        },
        {
            "type": "event",
            "data": _event(
                EventKind.TOOL_RESULT,
                {
                    "id": "call-1",
                    "name": "read_file",
                    "result": {"ok": True, "summary": "read README.md", "data": {}},
                },
            ).model_dump(mode="json"),
        },
        {
            "type": "message",
            "data": {"role": "assistant", "content": "The project is ready."},
        },
    ]

    history = AgentEventPresenter().present_history(SESSION_ID, records)

    final_messages = [
        item.data["content"] for item in history if item.type is ViewEventType.MESSAGE_FINAL
    ]
    assert final_messages == ["inspect the project", "The project is ready."]
    assert any(item.type is ViewEventType.ACTIVITY_UPSERT for item in history)
