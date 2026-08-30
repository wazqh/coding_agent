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


def test_steps_set_rejects_values_below_twelve() -> None:
    with pytest.raises(ValidationError):
        parse_client_request(
            {
                "protocol_version": 2,
                "type": "steps.set",
                "request_id": "steps-low",
                "value": 11,
            }
        )
