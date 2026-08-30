from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from coding_agent.branding import PRODUCT_NAME
from coding_agent.session import SessionStore
from coding_agent.web.app import _dispatch_request, create_web_app
from coding_agent.web.auth import LaunchAuth
from coding_agent.web.coordinator import TurnCoordinator
from coding_agent.web.protocol import (
    ChangesListRequest,
    FilePreviewRequest,
    PermissionsSetRequest,
    RuntimeStatusRequest,
    SessionResumeRequest,
    StepsSetRequest,
    ViewEventType,
)
from tests.web.test_coordinator import FakeRuntime


def _build_client(tmp_path: Path) -> tuple[TestClient, LaunchAuth]:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "assets").mkdir()
    (static_dir / "assets" / "app.js").write_text("export {};", encoding="utf-8")
    (static_dir / "index.html").write_text(
        "<title>__FORGE_PRODUCT_NAME__</title><main>__FORGE_PRODUCT_NAME__</main>",
        encoding="utf-8",
    )
    coordinator = TurnCoordinator()
    coordinator.attach_runtime(FakeRuntime(coordinator.handle_agent_event))
    coordinator.configure_workspace_services(
        workspace=tmp_path,
        sessions=SessionStore(tmp_path / "data"),
    )
    auth = LaunchAuth(host="testserver", origin="http://testserver")
    app = create_web_app(coordinator=coordinator, auth=auth, static_dir=static_dir)
    return TestClient(app), auth


def test_static_app_has_strict_local_security_headers(tmp_path: Path) -> None:
    client, _ = _build_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert f"<title>{PRODUCT_NAME}</title>" in response.text
    assert "__FORGE_PRODUCT_NAME__" not in response.text
    assert response.headers["content-security-policy"] == (
        "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
        "img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert client.get("/assets/app.js").status_code == 200


def test_bootstrap_exchanges_capability_for_strict_http_only_cookie(tmp_path: Path) -> None:
    client, auth = _build_client(tmp_path)
    headers = {"origin": "http://testserver"}

    denied = client.post(
        "/api/bootstrap",
        headers={**headers, "x-forge-capability": "wrong"},
    )
    accepted = client.post(
        "/api/bootstrap",
        headers={**headers, "x-forge-capability": auth.capability},
    )
    replayed = client.post(
        "/api/bootstrap",
        headers={**headers, "x-forge-capability": auth.capability},
    )

    assert denied.status_code == 403
    assert accepted.status_code == 204
    cookie = accepted.headers["set-cookie"].lower()
    assert "forge_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert replayed.status_code == 403


def test_authenticated_websocket_streams_turn_events(tmp_path: Path) -> None:
    client, auth = _build_client(tmp_path)
    origin = {"origin": "http://testserver"}
    response = client.post(
        "/api/bootstrap",
        headers={**origin, "x-forge-capability": auth.capability},
    )
    assert response.status_code == 204

    with client.websocket_connect("/ws", headers=origin) as websocket:
        websocket.send_json(
            {
                "protocol_version": 2,
                "type": "turn.start",
                "request_id": "request-1",
                "task": "hello",
            }
        )
        events = [websocket.receive_json() for _ in range(3)]

    assert [event["type"] for event in events] == [
        "turn.started",
        "message.delta",
        "turn.finished",
    ]
    assert events[1]["data"]["delta"] == "answer:hello"


def test_websocket_keeps_running_after_foreign_workspace_resume_is_rejected(
    tmp_path: Path,
) -> None:
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    foreign = SessionStore(tmp_path / "data").create({"workspace": str(other_workspace)})
    client, auth = _build_client(tmp_path)
    origin = {"origin": "http://testserver"}
    response = client.post(
        "/api/bootstrap",
        headers={**origin, "x-forge-capability": auth.capability},
    )
    assert response.status_code == 204

    with client.websocket_connect("/ws", headers=origin) as websocket:
        websocket.send_json(
            {
                "protocol_version": 2,
                "type": "session.resume",
                "request_id": "foreign-session",
                "session_id": foreign,
            }
        )
        rejected = websocket.receive_json()
        websocket.send_json(
            {
                "protocol_version": 2,
                "type": "initialize",
                "request_id": "still-connected",
                "last_seq": rejected["seq"],
            }
        )
        snapshot = websocket.receive_json()

    assert rejected["type"] == "error"
    assert rejected["data"]["recoverable"] is True
    assert snapshot["type"] == "snapshot"


def test_dispatches_session_restore_preview_and_recorded_changes(tmp_path: Path) -> None:
    sessions = SessionStore(tmp_path / "data")
    session_id = sessions.create({"workspace": str(tmp_path)})
    sessions.append_message(session_id, {"role": "user", "content": "历史任务"})
    (tmp_path / "demo.py").write_text("answer = 42", encoding="utf-8")
    coordinator = TurnCoordinator()
    runtime = FakeRuntime(coordinator.handle_agent_event)
    coordinator.attach_runtime(runtime)
    coordinator.configure_workspace_services(workspace=tmp_path, sessions=sessions)

    _dispatch_request(
        coordinator,
        SessionResumeRequest(type="session.resume", request_id="resume", session_id=session_id),
    )
    restored = coordinator.drain_events()
    assert [event.type.value for event in restored] == ["snapshot", "message.final"]
    assert restored[0].data["replace_timeline"] is True

    runtime.controllers[-1].working.diffs.append(
        "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-answer = 41\n+answer = 42\n"
    )
    _dispatch_request(
        coordinator,
        FilePreviewRequest(type="file.preview", request_id="preview", path="demo.py"),
    )
    _dispatch_request(
        coordinator,
        ChangesListRequest(type="changes.list", request_id="changes"),
    )
    events = coordinator.drain_events()

    assert events[0].type.value == "file.previewed"
    assert events[0].data["text"] == "answer = 42"
    assert events[1].type.value == "changes.updated"
    assert events[1].data["changes"][0]["path"] == "demo.py"


def test_dispatches_runtime_status_and_management_mutations() -> None:
    class Snapshot:
        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {"permissions": "auto", "steps": {"current": 40}}

    class Management:
        def __init__(self) -> None:
            self.permissions: list[str] = []
            self.steps: list[int] = []

        def snapshot(self) -> Snapshot:
            return Snapshot()

        def set_permissions(self, mode: str) -> Snapshot:
            self.permissions.append(mode)
            return Snapshot()

        def set_steps(self, value: int) -> Snapshot:
            self.steps.append(value)
            return Snapshot()

    coordinator = TurnCoordinator()
    coordinator.attach_runtime(FakeRuntime(coordinator.handle_agent_event))
    management = Management()
    coordinator.attach_management(management)  # type: ignore[arg-type]

    _dispatch_request(
        coordinator,
        RuntimeStatusRequest(type="runtime.status", request_id="status"),
    )
    _dispatch_request(
        coordinator,
        PermissionsSetRequest(
            type="permissions.set",
            request_id="permissions",
            mode="auto",
        ),
    )
    _dispatch_request(
        coordinator,
        StepsSetRequest(type="steps.set", request_id="steps", value=40),
    )

    events = coordinator.drain_events()
    assert management.permissions == ["auto"]
    assert management.steps == [40]
    assert [event.type for event in events] == [
        ViewEventType.RUNTIME_UPDATED,
        ViewEventType.RUNTIME_UPDATED,
        ViewEventType.COMMAND_COMPLETED,
        ViewEventType.RUNTIME_UPDATED,
        ViewEventType.COMMAND_COMPLETED,
    ]
    assert events[-1].data == {"command": "steps.set", "status": "completed"}
