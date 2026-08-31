from __future__ import annotations

from collections.abc import Callable, Iterator
from threading import Event
from typing import Any

import pytest
from conftest import FakeModel
from pydantic import BaseModel

from coding_agent.config import Settings
from coding_agent.context import estimate_request_tokens
from coding_agent.controller import AgentController
from coding_agent.events import AgentState, EventKind, ModelStreamEvent, ToolCall, ToolResult
from coding_agent.safety.approval import ApprovalDecision, ApprovalPolicy, ApprovalRequest
from coding_agent.safety.paths import sha256_file
from coding_agent.session import SessionError, SessionStore
from coding_agent.tools.base import AppliedChange, Tool, ToolContext
from coding_agent.tools.command import RunCommandArgs
from coding_agent.tools.filesystem import WriteFileTool
from coding_agent.tools.registry import ToolRegistry, default_registry
from coding_agent.verification import (
    VerificationContract,
    VerificationMode,
    VerificationProcedure,
)
from coding_agent.workspace_settings import VerificationCheck, WorkspaceSettingsStore


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
    tools: ToolRegistry | None = None,
    verification_commands: list[str] | None = None,
    verification_checks: list[VerificationCheck] | None = None,
    verification_enabled: bool | None = None,
    verification_agent_tdd: bool = False,
    verification_contract: VerificationContract | None = None,
    workspace_settings: WorkspaceSettingsStore | None = None,
) -> AgentController:
    sessions = SessionStore(settings.data_dir)
    return AgentController(
        settings=settings,
        model=model,  # type: ignore[arg-type]
        tools=tools or default_registry(),
        sessions=sessions,
        approval=approval or ApprovalPolicy("auto"),
        session_id=session_id,
        event_sink=events.append if events is not None else None,
        verification_commands=verification_commands or [],
        verification_checks=verification_checks or [],
        verification_enabled=verification_enabled,
        verification_agent_tdd=verification_agent_tdd,
        verification_contract=verification_contract,
        workspace_settings=workspace_settings,
        **({"monotonic": monotonic} if monotonic is not None else {}),
    )


def test_agent_tdd_mode_only_guides_the_agent_while_execution_stays_in_tools(
    settings: Settings,
) -> None:
    model = FakeModel([text_response("Tests are ready.")])
    controller = make_controller(
        settings,
        model,
        verification_enabled=True,
        verification_agent_tdd=True,
    )

    controller.run_turn("add a regression test")

    system_prompt = str(model.requests[0][0][0]["content"])
    assert "write or update focused tests" in system_prompt
    assert "Use run_verify with the returned rule id" in system_prompt
    assert "do not use run_command for verification" in system_prompt
    assert "never simulate or claim command execution" in system_prompt
    assert "separate test files" in system_prompt
    assert "configured working directory" in system_prompt
    assert "register_verification" in system_prompt


def test_tool_bearing_text_is_progress_and_final_text_follows_tool_results(
    settings: Settings,
) -> None:
    (settings.cwd / "README.md").write_text("hello\n", encoding="utf-8")
    events: list = []
    model = FakeModel(
        [
            [
                ModelStreamEvent(type="text_delta", text="I will inspect the file."),
                ModelStreamEvent(
                    type="tool_calls",
                    tool_calls=[
                        ToolCall(
                            id="read-one",
                            name="read_file",
                            arguments={"path": "README.md"},
                        )
                    ],
                ),
                ModelStreamEvent(type="done", finish_reason="tool_calls"),
            ],
            text_response("The file contains a greeting."),
        ]
    )
    controller = make_controller(settings, model, events=events)

    result = controller.run_turn("inspect README")

    assert result.status is AgentState.COMPLETED
    semantic = [
        (event.kind, event.data.get("phase"))
        for event in events
        if event.kind in {EventKind.TEXT, EventKind.TOOL_CALL, EventKind.TOOL_RESULT}
    ]
    assert semantic == [
        (EventKind.TEXT, "progress"),
        (EventKind.TOOL_CALL, None),
        (EventKind.TOOL_RESULT, None),
        (EventKind.TEXT, "final"),
    ]


def test_verification_contract_is_scoped_to_one_session_and_restored(
    settings: Settings,
) -> None:
    """Writing a contract into session A must not leak it into a new session B."""

    first = make_controller(settings, FakeModel([]))
    first.set_verification_contract(
        VerificationContract(
            mode=VerificationMode.CHECKS,
            checks=[
                VerificationCheck(
                    id="focused",
                    label="Focused tests",
                    kind="test",
                    command="python -m pytest tests/test_focused.py -q",
                    cwd="feature",
                    target_paths=["feature"],
                )
            ],
            procedures=[
                VerificationProcedure(
                    id="dependencies",
                    instruction="When dependencies change, rerun the existing test rule.",
                )
            ],
        )
    )

    second = make_controller(settings, FakeModel([]))
    resumed = make_controller(settings, FakeModel([]), session_id=first.session_id)

    assert second.verification_contract.mode is VerificationMode.OFF
    assert second.verification_contract.checks == []
    assert resumed.verification_contract.mode is VerificationMode.CHECKS
    assert resumed.verification_contract.checks[0].cwd == "feature"
    assert resumed.verification_contract.procedures[0].id == "dependencies"


def record_changed_path(controller: AgentController, turn_id: str, path: str) -> None:
    controller.working.changes.append(
        AppliedChange(
            path=path,
            kind="modified",
            diff=f"--- a/{path}\n+++ b/{path}\n",
            after_sha256="0" * 64,
            turn_id=turn_id,
        )
    )


def test_empty_agent_tdd_contract_and_manual_procedure_are_injected_into_prompt(
    settings: Settings,
) -> None:
    """Requiring a pre-existing rule would make the first Agent TDD turn impossible to save."""

    model = FakeModel([text_response("I will register a focused test rule.")])
    controller = make_controller(settings, model)
    controller.set_verification_contract(
        VerificationContract(
            mode=VerificationMode.AGENT_TDD,
            procedures=[
                VerificationProcedure(
                    id="dependency-regression",
                    instruction=(
                        "After dependency updates, rerun the session's existing "
                        "test and build rules."
                    ),
                )
            ],
        )
    )

    controller.run_turn("update a dependency safely")

    system_prompt = str(model.requests[0][0][0]["content"])
    assert "register_verification" in system_prompt
    assert "deterministic verification layer reruns applicable registered rules" in system_prompt
    assert "After dependency updates" in system_prompt
    assert controller.verification_contract.checks == []


def test_prompt_exposes_existing_verification_rules_with_manual_procedures(
    settings: Settings,
) -> None:
    model = FakeModel([text_response("I will preserve the focused verification contract.")])
    controller = make_controller(
        settings,
        model,
        verification_contract=VerificationContract(
            mode=VerificationMode.CHECKS,
            checks=[
                VerificationCheck(
                    id="dependency-build",
                    label="Dependency build",
                    kind="build",
                    command="npm run build",
                    cwd="web",
                    target_paths=["web/package.json", "web/package-lock.json"],
                )
            ],
            procedures=[
                VerificationProcedure(
                    id="dependency-regression",
                    instruction="After dependency updates, rerun the existing build rule.",
                )
            ],
        ),
    )

    controller.run_turn("update the dependency")

    system_prompt = str(model.requests[0][0][0]["content"])
    assert '"id": "dependency-build"' in system_prompt
    assert '"command": "npm run build"' in system_prompt
    assert '"cwd": "web"' in system_prompt
    assert '"target_paths": ["web/package.json", "web/package-lock.json"]' in system_prompt
    assert "follow throughout this turn" in system_prompt


def test_agent_registered_verification_runs_from_the_new_subproject(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="1 passed", data={"exit_code": 0})]
    )
    model = FakeModel(
        [
            tool_response(
                ToolCall(
                    id="write-test",
                    name="write_file",
                    arguments={
                        "path": "algorithm_practice/tests/test_trap.py",
                        "content": "def test_trap():\n    assert True\n",
                    },
                )
            ),
            tool_response(
                ToolCall(
                    id="register-check",
                    name="register_verification",
                    arguments={
                        "label": "Algorithm tests",
                        "kind": "test",
                        "command": "python -m pytest tests -q",
                        "cwd": "algorithm_practice",
                        "timeout_seconds": 90,
                    },
                )
            ),
            text_response("Implemented and verified."),
        ]
    )
    store = WorkspaceSettingsStore(
        data_dir=settings.data_dir,
        workspace=settings.cwd,
    )
    controller = make_controller(
        settings,
        model,
        tools=verification_registry(verifier, include_registration=True),
        workspace_settings=store,
        verification_contract=VerificationContract(mode=VerificationMode.AGENT_TDD),
    )

    result = controller.run_turn("Implement an isolated rain-water exercise with tests")

    assert result.status is AgentState.COMPLETED
    assert verifier.arguments == [
        {
            "command": "python -m pytest tests -q",
            "cwd": "algorithm_practice",
            "timeout": 90,
        }
    ]
    verification_records = [
        record
        for record in controller.sessions.replay(controller.session_id)
        if record["type"] == "verification_result"
    ]
    assert verification_records[-1]["data"]["status"] == "passed"
    assert verification_records[-1]["data"]["manual"] is False
    assert verification_records[-1]["data"]["target_paths"] == [
        "algorithm_practice/tests/test_trap.py"
    ]
    assert store.load().verification.enabled is False
    assert controller.verification_contract.mode is VerificationMode.AGENT_TDD
    assert controller.verification_contract.checks[0].source == "agent"
    assert controller.verification_contract.checks[0].target_paths == ["algorithm_practice"]


def test_agent_registration_updates_an_equivalent_session_rule_without_duplication(
    settings: Settings,
) -> None:
    controller = make_controller(
        settings,
        FakeModel([]),
        verification_contract=VerificationContract(
            mode=VerificationMode.AGENT_TDD,
            checks=[
                VerificationCheck(
                    id="manual-rule",
                    label="Existing tests",
                    command="python -m pytest -q",
                    cwd="feature",
                    target_paths=["feature/src"],
                )
            ],
        ),
    )
    replacement = VerificationCheck(
        id="agent-focused-rule",
        label="Focused feature tests",
        command="python -m pytest -q",
        cwd="feature",
        source="agent",
        target_paths=["feature"],
    )

    controller._register_verification_check(replacement)

    assert controller.verification_contract.checks == [replacement]


def test_agent_registration_enables_checks_mode_and_enforces_rule_limit(
    settings: Settings,
) -> None:
    controller = make_controller(
        settings,
        FakeModel([]),
        verification_contract=VerificationContract(mode=VerificationMode.OFF),
    )
    first = VerificationCheck(
        id="agent-first",
        label="Focused tests",
        command="python -m pytest -q",
        cwd="feature",
        source="agent",
    )

    controller._register_verification_check(first)

    assert controller.verification_contract.mode is VerificationMode.CHECKS
    full_contract = VerificationContract(
        mode=VerificationMode.CHECKS,
        checks=[
            VerificationCheck(
                id=f"rule-{index}",
                label=f"Rule {index}",
                command=f"python -m pytest tests/test_{index}.py -q",
            )
            for index in range(8)
        ],
    )
    controller.set_verification_contract(full_contract)
    with pytest.raises(ValueError, match="at most 8"):
        controller._register_verification_check(
            VerificationCheck(
                id="ninth",
                label="Ninth rule",
                command="python -m pytest tests/test_ninth.py -q",
            )
        )


def test_automatic_verification_only_runs_checks_covering_changed_paths(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="1 passed", data={"exit_code": 0})]
    )
    model = FakeModel(
        [
            tool_response(
                ToolCall(
                    id="write-algorithm",
                    name="write_file",
                    arguments={
                        "path": "algorithm_practice/tests/test_trap.py",
                        "content": "def test_trap():\n    assert True\n",
                    },
                )
            ),
            text_response("Implemented and verified."),
        ]
    )
    controller = make_controller(
        settings,
        model,
        tools=verification_registry(verifier),
        verification_enabled=True,
        verification_checks=[
            VerificationCheck(
                id="algorithm-tests",
                label="Algorithm tests",
                kind="test",
                command="python -m pytest tests -q",
                cwd="algorithm_practice",
                target_paths=["algorithm_practice"],
            ),
            VerificationCheck(
                id="web-tests",
                label="Web tests",
                kind="test",
                command="npm test",
                cwd="web",
                target_paths=["web"],
            ),
        ],
    )

    result = controller.run_turn("add an algorithm regression test")

    assert result.status is AgentState.COMPLETED
    assert verifier.arguments == [
        {
            "command": "python -m pytest tests -q",
            "cwd": "algorithm_practice",
            "timeout": 120,
        }
    ]
    assert any(
        record["type"] == "event"
        and record["data"]["kind"] == EventKind.VERIFICATION.value
        and record["data"]["data"]["status"] == "passed"
        for record in controller.sessions.replay(controller.session_id)
    )


def test_manual_verification_passes_structured_cwd_and_timeout_to_run_command(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="tests passed", data={"exit_code": 0})]
    )
    events: list = []
    controller = make_controller(
        settings,
        FakeModel([]),
        tools=verification_registry(verifier),
        events=events,
        verification_checks=[
            VerificationCheck(
                id="algorithm-tests",
                label="Algorithm tests",
                kind="test",
                command="python -m pytest tests -q",
                cwd="algorithm_practice",
                timeout_seconds=90,
            )
        ],
        verification_enabled=True,
    )
    record_changed_path(controller, "structured-turn", "algorithm_practice/example.py")

    result = controller.run_verification("structured-turn")

    assert result.status == "passed"
    assert verifier.arguments == [
        {
            "command": "python -m pytest tests -q",
            "cwd": "algorithm_practice",
            "timeout": 90,
        }
    ]
    finished = next(
        event
        for event in events
        if event.kind is EventKind.TOOL_RESULT and event.data.get("verification") is True
    )
    assert finished.data["verification_check"]["id"] == "algorithm-tests"
    assert finished.data["verification_status"] == "passed"


@pytest.mark.parametrize(
    ("tool_result", "expected_status"),
    [
        (ToolResult(ok=False, code="COMMAND_FAILED", summary="tests failed"), "test_failed"),
        (ToolResult(ok=False, code="TOOL_ERROR", summary="cwd missing"), "configuration_error"),
        (ToolResult(ok=False, code="APPROVAL_DENIED", summary="denied"), "approval_denied"),
        (ToolResult(ok=False, code="TIMEOUT", summary="timed out"), "timed_out"),
        (ToolResult(ok=False, code="CANCELLED", summary="cancelled"), "cancelled"),
    ],
)
def test_manual_verification_classifies_terminal_outcomes(
    settings: Settings,
    tool_result: ToolResult,
    expected_status: str,
) -> None:
    controller = make_controller(
        settings,
        FakeModel([]),
        tools=verification_registry(FakeVerificationTool([tool_result])),
        verification_commands=["python -m pytest -q"],
    )
    record_changed_path(controller, "classified-turn", "src/example.py")

    result = controller.run_verification("classified-turn")

    assert result.status == expected_status


def test_manual_verification_runs_configured_commands_without_calling_the_model(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="24 passed", data={"exit_code": 0})]
    )
    model = FakeModel([])
    events: list = []
    controller = make_controller(
        settings,
        model,
        tools=verification_registry(verifier),
        events=events,
        verification_commands=["python -m pytest -q"],
        verification_enabled=False,
    )
    record_changed_path(controller, "turn-to-verify", "src/example.py")

    result = controller.run_verification("turn-to-verify")

    assert result.status == "passed"
    assert verifier.commands == ["python -m pytest -q"]
    assert model.requests == []
    assert any(
        event.kind is EventKind.TOOL_RESULT
        and event.turn_id == "turn-to-verify"
        and event.data.get("verification") is True
        for event in events
    )


def test_manual_verification_is_limited_to_the_selected_turn_and_persists_result(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="focused tests passed")]
    )
    controller = make_controller(
        settings,
        FakeModel([]),
        tools=verification_registry(verifier),
        verification_checks=[
            VerificationCheck(
                id="web-tests",
                label="Web tests",
                kind="test",
                command="npm test",
                cwd="web",
                target_paths=["web"],
            ),
            VerificationCheck(
                id="python-tests",
                label="Python tests",
                kind="test",
                command="python -m pytest -q",
                target_paths=["src"],
            ),
        ],
        verification_enabled=True,
    )
    record_changed_path(controller, "web-turn", "web/src/app/App.tsx")
    record_changed_path(controller, "python-turn", "src/coding_agent/controller.py")

    result = controller.run_verification("web-turn")

    assert result.status == "passed"
    assert verifier.commands == ["npm test"]
    records = controller.sessions.replay(controller.session_id)
    verification_result = records[-1]
    assert verification_result["type"] == "verification_result"
    assert verification_result["data"]["turn_id"] == "web-turn"
    assert verification_result["data"]["target_paths"] == ["web/src/app/App.tsx"]


def test_manual_verification_skips_a_turn_without_file_changes(settings: Settings) -> None:
    verifier = FakeVerificationTool([ToolResult(ok=True, code="OK", summary="must not execute")])
    controller = make_controller(
        settings,
        FakeModel([]),
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
        verification_enabled=True,
    )

    result = controller.run_verification("read-only-turn")

    assert result.status == "not_needed"
    assert verifier.commands == []
    record = controller.sessions.replay(controller.session_id)[-1]
    assert record["type"] == "verification_result"
    assert record["data"]["status"] == "not_needed"


def test_manual_verification_reports_no_matching_rule_and_honors_root_scope(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="root checks passed", data={"exit_code": 0})]
    )
    controller = make_controller(
        settings,
        FakeModel([]),
        tools=verification_registry(verifier),
        verification_checks=[
            VerificationCheck(
                id="web-only",
                label="Web tests",
                command="npm test",
                cwd="web",
                target_paths=["web"],
            )
        ],
        verification_enabled=True,
    )
    record_changed_path(controller, "python-turn", "src/coding_agent/controller.py")

    missing = controller.run_verification("python-turn")

    assert missing.status == "not_configured"
    assert verifier.commands == []
    controller.set_verification_contract(
        VerificationContract(
            mode=VerificationMode.CHECKS,
            checks=[
                VerificationCheck(
                    id="root",
                    label="Root checks",
                    command="python -m pytest -q",
                    target_paths=["."],
                )
            ],
        )
    )

    passed = controller.run_verification("python-turn")

    assert passed.status == "passed"
    assert verifier.commands == ["python -m pytest -q"]


def test_manual_verification_can_cancel_before_the_first_rule(settings: Settings) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="must not execute", data={"exit_code": 0})]
    )
    controller = make_controller(
        settings,
        FakeModel([]),
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
        verification_enabled=True,
    )
    record_changed_path(controller, "cancelled-turn", "src/example.py")
    cancelled = Event()
    cancelled.set()

    result = controller.run_verification("cancelled-turn", cancel_event=cancelled)

    assert result.status == "cancelled"
    assert verifier.commands == []


class FakeVerificationTool(Tool):
    name = "run_command"
    description = "Test verification command runner."
    args_model = RunCommandArgs

    def __init__(
        self,
        results: list[ToolResult],
        *,
        require_approval: bool = False,
        after_execute: Callable[[], None] | None = None,
    ) -> None:
        self.results = list(results)
        self.commands: list[str] = []
        self.arguments: list[dict[str, object]] = []
        self.require_approval = require_approval
        self.after_execute = after_execute

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = RunCommandArgs.model_validate(args)
        self.commands.append(values.command)
        self.arguments.append(values.model_dump())
        if (
            self.require_approval
            and not context.is_verification_command_authorized(values.command, values.cwd)
            and not context.approve(
                ApprovalRequest(
                    action="run_command",
                    subject=values.command,
                    summary=f"run command: {values.command}",
                )
            )
        ):
            return ToolResult(ok=False, code="APPROVAL_DENIED", summary="command denied")
        result = self.results.pop(0)
        if self.after_execute is not None:
            self.after_execute()
        return result


def verification_registry(
    tool: FakeVerificationTool,
    *,
    include_registration: bool = False,
) -> ToolRegistry:
    tools: list[Tool] = [WriteFileTool(), tool]
    if include_registration:
        from coding_agent.tools.verification import RegisterVerificationTool, RunVerifyTool

        tools.extend([RegisterVerificationTool(), RunVerifyTool()])
    return ToolRegistry(tools)


def test_agent_run_verify_uses_registered_rule_and_persists_gui_evidence(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="focused tests passed", data={"exit_code": 0})]
    )
    model = FakeModel(
        [
            tool_response(
                ToolCall(
                    id="register",
                    name="register_verification",
                    arguments={
                        "label": "Focused tests",
                        "command": "python -m pytest -q",
                        "cwd": ".",
                        "target_paths": ["."],
                    },
                )
            ),
            tool_response(
                ToolCall(
                    id="verify",
                    name="run_verify",
                    arguments={"rule_id": "agent-2297b1ce05dc1b19"},
                )
            ),
            text_response("Verification passed."),
        ]
    )
    events: list = []
    controller = make_controller(
        settings,
        model,
        tools=verification_registry(verifier, include_registration=True),
        events=events,
        verification_contract=VerificationContract(mode=VerificationMode.AGENT_TDD),
    )

    result = controller.run_turn("inspect and verify")

    assert result.status is AgentState.COMPLETED
    assert verifier.commands == ["python -m pytest -q"]
    assert any(event.kind is EventKind.VERIFICATION for event in events)
    verification_result = next(
        event
        for event in events
        if event.kind is EventKind.TOOL_RESULT and event.data.get("name") == "run_verify"
    )
    assert verification_result.data["verification_status"] == "passed"


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


def test_completed_turn_warns_when_its_visible_plan_was_not_closed(settings: Settings) -> None:
    plan_call = ToolCall(
        id="plan",
        name="update_plan",
        arguments={
            "plan": [
                {"step": "Inspect", "status": "completed"},
                {"step": "Explain", "status": "in_progress"},
                {"step": "Verify", "status": "pending"},
            ]
        },
    )
    model = FakeModel([tool_response(plan_call), text_response("Here is the final answer.")])
    events: list = []
    controller = make_controller(settings, model, events=events)

    result = controller.run_turn("make and follow a plan")

    assert result.status is AgentState.COMPLETED
    warning = next(
        event
        for event in events
        if event.kind is EventKind.WARNING and event.data.get("code") == "PLAN_INCOMPLETE"
    )
    assert warning.data["completed"] == 1
    assert warning.data["total"] == 3
    system_prompt = str(model.requests[0][0][0]["content"])
    assert "final response" in system_prompt
    assert "update the visible plan" in system_prompt


def test_completed_turn_does_not_warn_about_an_older_unfinished_plan(settings: Settings) -> None:
    events: list = []
    controller = make_controller(
        settings, FakeModel([text_response("A new answer.")]), events=events
    )
    controller.working.plan = [{"step": "Old task", "status": "in_progress"}]
    controller.working.plan_turn_id = "older-turn"

    result = controller.run_turn("unrelated follow-up")

    assert result.status is AgentState.COMPLETED
    assert not any(
        event.kind is EventKind.WARNING and event.data.get("code") == "PLAN_INCOMPLETE"
        for event in events
    )


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


def test_approval_events_are_correlated_with_the_tool_operation(settings: Settings) -> None:
    call = ToolCall(
        id="write-operation",
        name="write_file",
        arguments={"path": "created.txt", "content": "content"},
    )
    events: list = []
    controller = make_controller(
        settings,
        FakeModel([tool_response(call), text_response("done")]),
        approval=ApprovalPolicy(
            "prompt",
            callback=lambda _: ApprovalDecision.ALLOW_ONCE,
        ),
        events=events,
    )

    controller.run_turn("create a file")

    approval_events = [event for event in events if event.kind is EventKind.APPROVAL]
    assert len(approval_events) == 2
    assert {event.data["operation_id"] for event in approval_events} == {"write-operation"}


def test_recorded_changes_survive_session_restore_with_safe_undo_data(
    settings: Settings,
) -> None:
    source = settings.cwd / "demo.txt"
    source.write_text("before\n", encoding="utf-8")
    call = ToolCall(
        id="edit-operation",
        name="write_file",
        arguments={
            "path": "demo.txt",
            "content": "after\n",
            "expected_sha256": sha256_file(source),
        },
    )
    model = FakeModel([tool_response(call), text_response("done")])
    controller = make_controller(settings, model)
    controller.run_turn("update the file")
    session_id = controller.session_id

    restored = make_controller(settings, FakeModel([]), session_id=session_id)

    assert len(restored.working.changes) == 1
    change = restored.working.changes[0]
    assert change.path == "demo.txt"
    assert (change.before_text or "").splitlines() == ["before"]
    assert change.review_status == "pending"


def test_verification_hooks_do_not_run_when_the_turn_makes_no_change(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool([ToolResult(ok=True, code="OK", summary="passed")])
    controller = make_controller(
        settings,
        FakeModel([text_response("Nothing to change.")]),
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
    )

    result = controller.run_turn("inspect only")

    assert result.status is AgentState.COMPLETED
    assert verifier.commands == []


def test_verification_hook_runs_after_a_changed_turn_and_is_visible_as_validation(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="tests passed", data={"exit_code": 0})]
    )
    events: list = []
    controller = make_controller(
        settings,
        FakeModel(
            [
                tool_response(
                    ToolCall(
                        id="write",
                        name="write_file",
                        arguments={"path": "demo.txt", "content": "first\n"},
                    )
                ),
                text_response("Implemented and verified."),
            ]
        ),
        events=events,
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
    )

    result = controller.run_turn("create demo")

    assert result.status is AgentState.COMPLETED
    assert result.tool_steps == 2
    assert verifier.commands == ["python -m pytest -q"]
    validation = next(
        event
        for event in events
        if event.kind is EventKind.TOOL_RESULT and event.data.get("verification") is True
    )
    assert validation.data["name"] == "run_command"
    assert validation.data["result"]["ok"] is True


def test_failed_verification_is_fed_back_to_the_model_before_a_bounded_repair(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [
            ToolResult(
                ok=False,
                code="COMMAND_FAILED",
                summary="tests failed",
                data={"exit_code": 1, "stderr": "assertion failed"},
            ),
            ToolResult(ok=True, code="OK", summary="tests passed", data={"exit_code": 0}),
        ]
    )
    model = FakeModel(
        [
            tool_response(
                ToolCall(
                    id="write-1",
                    name="write_file",
                    arguments={"path": "demo.txt", "content": "first\n"},
                )
            ),
            text_response("Initial implementation."),
            tool_response(
                ToolCall(
                    id="write-2",
                    name="write_file",
                    arguments={"path": "demo.txt", "content": "fixed\n"},
                )
            ),
            text_response("Fixed and verified."),
        ]
    )
    events: list = []
    controller = make_controller(
        settings,
        model,
        events=events,
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
    )

    result = controller.run_turn("create a passing demo")

    assert result.status is AgentState.COMPLETED
    assert verifier.commands == ["python -m pytest -q", "python -m pytest -q"]
    visible_text = "".join(
        str(event.data.get("delta", "")) for event in events if event.kind is EventKind.TEXT
    )
    assert "Initial implementation." not in visible_text
    assert visible_text.endswith("Fixed and verified.")
    repair_request = model.requests[2][0]
    verification_call = next(
        message
        for message in repair_request
        if message.get("role") == "assistant"
        and message.get("tool_calls")
        and message["tool_calls"][0]["id"].startswith("verification-")
    )
    verification_result = next(
        message
        for message in repair_request
        if message.get("role") == "tool"
        and message.get("tool_call_id") == verification_call["tool_calls"][0]["id"]
    )
    assert "tests failed" in verification_result["content"]


def test_verification_configuration_errors_stop_without_asking_the_model_to_repair(
    settings: Settings,
) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=False, code="TOOL_ERROR", summary="configured cwd does not exist")]
    )
    model = FakeModel(
        [
            tool_response(
                ToolCall(
                    id="write",
                    name="write_file",
                    arguments={"path": "demo.txt", "content": "content\n"},
                )
            ),
            text_response("Implementation complete."),
        ]
    )
    controller = make_controller(
        settings,
        model,
        tools=verification_registry(verifier),
        verification_checks=[
            VerificationCheck(
                id="missing-project",
                label="Nested tests",
                command="python -m pytest -q",
                cwd="missing",
            )
        ],
    )

    result = controller.run_turn("create demo")

    assert result.status is AgentState.FAILED
    assert result.reason == "verification configuration error"
    assert len(model.requests) == 2


def test_verification_stops_after_two_repair_opportunities(settings: Settings) -> None:
    verifier = FakeVerificationTool(
        [
            ToolResult(ok=False, code="COMMAND_FAILED", summary=f"failure {index}")
            for index in range(3)
        ]
    )
    model = FakeModel(
        [
            tool_response(
                ToolCall(
                    id="write",
                    name="write_file",
                    arguments={"path": "demo.txt", "content": "broken\n"},
                )
            ),
            text_response("Attempt one."),
            text_response("Attempt two."),
            text_response("Attempt three."),
        ]
    )
    controller = make_controller(
        settings,
        model,
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
    )

    result = controller.run_turn("create demo")

    assert result.status is AgentState.FAILED
    assert result.reason == "verification failed after two repair attempts"
    assert len(verifier.commands) == 3


def test_saved_verification_rule_does_not_prompt_twice(settings: Settings) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="passed")],
        require_approval=True,
    )
    approvals: list[ApprovalRequest] = []
    events: list = []
    controller = make_controller(
        settings,
        FakeModel(
            [
                tool_response(
                    ToolCall(
                        id="write",
                        name="write_file",
                        arguments={"path": "demo.txt", "content": "content\n"},
                    )
                ),
                text_response("done"),
            ]
        ),
        approval=ApprovalPolicy(
            "prompt",
            callback=lambda request: approvals.append(request) or ApprovalDecision.ALLOW_ONCE,
        ),
        events=events,
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
    )

    result = controller.run_turn("create demo")

    assert result.status is AgentState.COMPLETED
    assert [request.action for request in approvals] == ["write_file"]
    verification_approvals = [
        event
        for event in events
        if event.kind is EventKind.APPROVAL
        and str(event.data.get("operation_id", "")).startswith("verification-")
    ]
    assert verification_approvals == []


def test_manual_saved_verification_rule_does_not_prompt_again(settings: Settings) -> None:
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="passed")],
        require_approval=True,
    )
    approvals: list[ApprovalRequest] = []
    controller = make_controller(
        settings,
        FakeModel([]),
        approval=ApprovalPolicy(
            "prompt",
            callback=lambda request: approvals.append(request) or ApprovalDecision.DENY,
        ),
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
    )
    record_changed_path(controller, "manual-turn", "src/example.py")

    result = controller.run_verification("manual-turn")

    assert result.status == "passed"
    assert verifier.commands == ["python -m pytest -q"]
    assert approvals == []


def test_verification_stops_when_the_turn_is_cancelled_during_a_check(
    settings: Settings,
) -> None:
    cancel_event = Event()
    verifier = FakeVerificationTool(
        [ToolResult(ok=True, code="OK", summary="cancelled after completion")],
        after_execute=cancel_event.set,
    )
    controller = make_controller(
        settings,
        FakeModel(
            [
                tool_response(
                    ToolCall(
                        id="write",
                        name="write_file",
                        arguments={"path": "demo.txt", "content": "content\n"},
                    )
                ),
                text_response("done"),
            ]
        ),
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q"],
    )

    result = controller.run_turn("create demo", cancel_event=cancel_event)

    assert result.status is AgentState.CANCELLED
    assert result.exit_code == 130


def test_verification_commands_share_the_existing_tool_step_budget(settings: Settings) -> None:
    settings.agent.max_steps = 2
    verifier = FakeVerificationTool([ToolResult(ok=True, code="OK", summary="first passed")])
    controller = make_controller(
        settings,
        FakeModel(
            [
                tool_response(
                    ToolCall(
                        id="write",
                        name="write_file",
                        arguments={"path": "demo.txt", "content": "content\n"},
                    )
                ),
                text_response("done"),
            ]
        ),
        tools=verification_registry(verifier),
        verification_commands=["python -m pytest -q", "python -m ruff check ."],
    )

    result = controller.run_turn("create demo")

    assert result.status is AgentState.FAILED
    assert result.tool_steps == 2
    assert result.reason == "verification could not run within the tool step budget"
    assert verifier.commands == ["python -m pytest -q"]


def test_context_breakdown_uses_complete_request_categories(settings: Settings) -> None:
    controller = make_controller(settings, FakeModel([]))
    controller._last_system_prompt = "system instructions"
    controller.conversation = [{"role": "user", "content": "hello"}]
    controller.last_context_tokens = 100

    breakdown = controller.context_breakdown()

    assert breakdown["system_and_project"] > 0
    assert breakdown["conversation_and_results"] > 0
    assert breakdown["tool_schemas"] > 0
    assert breakdown["other"] >= 0


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


def test_provider_history_synthesizes_missing_tool_results_in_call_order() -> None:
    prepared = AgentController._messages_for_model(
        [
            {"role": "system", "content": "instructions"},
            {"role": "user", "content": "continue"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-one",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    },
                    {
                        "id": "call-two",
                        "type": "function",
                        "function": {"name": "update_plan", "arguments": "{}"},
                    },
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-one",
                "name": "read_file",
                "content": '{"ok":true}',
            },
            {"role": "user", "content": "next"},
        ]
    )

    assert [message["role"] for message in prepared] == [
        "system",
        "user",
        "assistant",
        "tool",
        "tool",
        "user",
    ]
    assert [message.get("tool_call_id") for message in prepared[3:5]] == [
        "call-one",
        "call-two",
    ]
    assert "INCOMPLETE_TOOL_CALL" in str(prepared[4]["content"])


def test_budget_exhausted_session_compacts_the_complete_turn_before_continuing(
    settings: Settings,
) -> None:
    store = SessionStore(settings.data_dir)
    session_id = store.create(
        {"workspace": str(settings.cwd.resolve()), "model": settings.model.name}
    )
    marker = "oversized-observation-" * 2_000
    store.append(session_id, "message", {"role": "user", "content": "finish the task"})
    store.append(session_id, "message", {"role": "assistant", "content": marker})
    store.append(
        session_id,
        "termination",
        {"status": "failed", "reason": "tool step budget exhausted", "exit_code": 1},
    )

    model = FakeModel([text_response("continued safely")])
    resumed = make_controller(settings, model, session_id=session_id)
    result = resumed.run_turn("continue")

    assert result.status is AgentState.COMPLETED
    request = model.requests[0][0]
    assert marker not in str(request)
    assert any(
        message.get("role") == "system" and "Conversation summary" in str(message.get("content"))
        for message in request
    )
