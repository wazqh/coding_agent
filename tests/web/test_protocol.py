from __future__ import annotations

import pytest
from pydantic import ValidationError

from coding_agent.web.protocol import (
    ApprovalResolveRequest,
    PermissionsSetRequest,
    StepsSetRequest,
    TurnStartRequest,
    ViewEvent,
    ViewEventType,
    parse_client_request,
)


def test_protocol_accepts_closed_request_shapes() -> None:
    turn = parse_client_request(
        {
            "protocol_version": 2,
            "type": "turn.start",
            "request_id": "request-1",
            "task": "Fix the validation bug",
        }
    )
    approval = parse_client_request(
        {
            "protocol_version": 2,
            "type": "approval.resolve",
            "request_id": "request-2",
            "approval_id": "approval-1",
            "decision": "allow_once",
        }
    )
    undo = parse_client_request(
        {
            "protocol_version": 2,
            "type": "change.undo",
            "request_id": "request-3",
            "change_id": "a" * 32,
        }
    )
    delete_session = parse_client_request(
        {
            "protocol_version": 2,
            "type": "session.delete",
            "request_id": "request-4",
            "session_id": "b" * 24,
        }
    )

    assert isinstance(turn, TurnStartRequest)
    assert turn.task == "Fix the validation bug"
    assert isinstance(approval, ApprovalResolveRequest)
    assert approval.decision.value == "allow_once"
    assert type(undo).__name__ == "ChangeUndoRequest"
    assert undo.change_id == "a" * 32
    assert type(delete_session).__name__ == "SessionDeleteRequest"
    assert delete_session.session_id == "b" * 24


@pytest.mark.parametrize(
    "payload",
    [
        {"protocol_version": 2, "type": "run_tool", "request_id": "r1"},
        {"protocol_version": 1, "type": "initialize", "request_id": "r1"},
        {"protocol_version": 2, "type": "initialize", "request_id": ""},
        {
            "protocol_version": 2,
            "type": "session.resume",
            "request_id": "r1",
            "session_id": "../escape",
        },
        {
            "protocol_version": 2,
            "type": "approval.resolve",
            "request_id": "r1",
            "approval_id": "a1",
            "decision": "always",
        },
        {
            "protocol_version": 2,
            "type": "turn.start",
            "request_id": "r1",
            "task": "x" * 100_001,
        },
        {
            "protocol_version": 2,
            "type": "change.undo",
            "request_id": "r1",
            "change_id": "../../workspace",
        },
        {
            "protocol_version": 2,
            "type": "session.delete",
            "request_id": "r1",
            "session_id": "../escape",
        },
    ],
)
def test_protocol_rejects_unknown_or_unbounded_requests(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse_client_request(payload)


def test_view_event_serializes_without_secret_fields() -> None:
    event = ViewEvent(
        type=ViewEventType.TURN_STARTED,
        seq=7,
        session_id="a" * 24,
        turn_id="turn-1",
        data={"model": "gemini-flash"},
    )

    assert event.model_dump(mode="json") == {
        "protocol_version": 2,
        "type": "turn.started",
        "seq": 7,
        "session_id": "a" * 24,
        "turn_id": "turn-1",
        "data": {"model": "gemini-flash"},
    }


@pytest.mark.parametrize(
    ("request_type", "extra", "expected_type"),
    [
        ("runtime.status", {}, "runtime.status"),
        ("steps.get", {}, "steps.get"),
        ("steps.set", {"value": 40}, "steps.set"),
        ("steps.reset", {}, "steps.reset"),
        (
            "verification.set",
            {"commands": ["python -m pytest -q"]},
            "verification.set",
        ),
        ("permissions.get", {}, "permissions.get"),
        ("permissions.set", {"mode": "auto"}, "permissions.set"),
        ("plan.get", {}, "plan.get"),
        (
            "model.provider.upsert",
            {
                "provider": "open-router",
                "base_url": "https://openrouter.ai/api/v1",
                "model": "vendor/model",
                "compatibility": "openai",
            },
            "model.provider.upsert",
        ),
        (
            "model.provider.delete",
            {"provider": "open-router", "confirm": True},
            "model.provider.delete",
        ),
        (
            "model.update",
            {
                "provider": "glm",
                "original_model": "glm-5.2-flash",
                "model": "glm-5.2-air",
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "compatibility": "openai",
            },
            "model.update",
        ),
        (
            "model.delete",
            {"provider": "glm", "model": "glm-5.2-flash", "confirm": True},
            "model.delete",
        ),
        ("model.probe", {}, "model.probe"),
        (
            "skills.draft",
            {"requirement": "Review workspace boundaries", "template": "review"},
            "skills.draft",
        ),
        (
            "skills.create",
            {
                "scope": "repo",
                "name": "boundary-review",
                "description": "Review workspace boundaries.",
                "instructions": "# Workflow\n\nRead the rules and review the change.",
            },
            "skills.create",
        ),
    ],
)
def test_protocol_v2_accepts_management_requests(
    request_type: str,
    extra: dict[str, object],
    expected_type: str,
) -> None:
    request = parse_client_request(
        {
            "protocol_version": 2,
            "type": request_type,
            "request_id": "management-1",
            **extra,
        }
    )

    assert request.type == expected_type
    if request_type == "steps.set":
        assert isinstance(request, StepsSetRequest)
    if request_type == "permissions.set":
        assert isinstance(request, PermissionsSetRequest)


@pytest.mark.parametrize("value", [29, 1000])
def test_steps_set_rejects_values_outside_supported_range(value: int) -> None:
    with pytest.raises(ValidationError):
        parse_client_request(
            {
                "protocol_version": 2,
                "type": "steps.set",
                "request_id": "steps-invalid",
                "value": value,
            }
        )


def test_skill_creation_rejects_invalid_names_and_unbounded_drafts() -> None:
    with pytest.raises(ValidationError):
        parse_client_request(
            {
                "protocol_version": 2,
                "type": "skills.create",
                "request_id": "skill-invalid",
                "scope": "repo",
                "name": "../escape",
                "description": "Invalid path.",
                "instructions": "Do not write outside the root.",
            }
        )
    with pytest.raises(ValidationError):
        parse_client_request(
            {
                "protocol_version": 2,
                "type": "skills.draft",
                "request_id": "skill-long",
                "requirement": "x" * 4001,
                "template": "custom",
            }
        )


@pytest.mark.parametrize(
    "commands",
    [[""], ["python -m pytest\nRemove-Item -Recurse ."], ["x" * 20_001]],
)
def test_verification_set_rejects_malformed_commands(commands: list[str]) -> None:
    with pytest.raises(ValidationError):
        parse_client_request(
            {
                "protocol_version": 2,
                "type": "verification.set",
                "request_id": "verification-invalid",
                "commands": commands,
            }
        )


def test_verification_requests_expose_mode_and_manual_run_target() -> None:
    configured = parse_client_request(
        {
            "protocol_version": 2,
            "type": "verification.set",
            "request_id": "verification-mode",
            "enabled": True,
            "agent_tdd": True,
            "commands": ["python -m pytest -q"],
        }
    )
    manual = parse_client_request(
        {
            "protocol_version": 2,
            "type": "verification.run",
            "request_id": "verification-run",
            "turn_id": "turn-123",
        }
    )

    assert configured.enabled is True
    assert configured.agent_tdd is True
    assert manual.turn_id == "turn-123"


def test_verification_request_accepts_an_empty_agent_tdd_contract_with_procedures() -> None:
    configured = parse_client_request(
        {
            "protocol_version": 2,
            "type": "verification.set",
            "request_id": "verification-contract",
            "mode": "agent_tdd",
            "checks": [],
            "procedures": [
                {
                    "id": "dependency-regression",
                    "instruction": "After dependencies change, rerun the existing rules.",
                }
            ],
        }
    )

    assert configured.mode == "agent_tdd"
    assert configured.enabled is True
    assert configured.agent_tdd is True
    assert configured.procedures[0].id == "dependency-regression"


def test_verification_set_accepts_project_aware_checks() -> None:
    configured = parse_client_request(
        {
            "protocol_version": 2,
            "type": "verification.set",
            "request_id": "verification-checks",
            "enabled": True,
            "agent_tdd": True,
            "checks": [
                {
                    "id": "algorithm-tests",
                    "label": "Algorithm tests",
                    "kind": "test",
                    "command": "python -m pytest tests -q",
                    "cwd": "algorithm_practice",
                    "timeout_seconds": 90,
                    "enabled": True,
                }
            ],
        }
    )

    assert configured.type == "verification.set"
    assert configured.checks[0].cwd == "algorithm_practice"
    assert configured.checks[0].timeout_seconds == 90
