from __future__ import annotations

import asyncio
import html
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from coding_agent.branding import PRODUCT_NAME
from coding_agent.web.auth import LaunchAuth
from coding_agent.web.coordinator import CoordinatorError, TurnCoordinator
from coding_agent.web.preview import PreviewError
from coding_agent.web.protocol import (
    ApprovalResolveRequest,
    ChangesListRequest,
    ChangeUndoRequest,
    CompletionQueryRequest,
    ConfigGetRequest,
    ContextCompactRequest,
    ContextGetRequest,
    FilePreviewRequest,
    InitializeRequest,
    MemoryClearRequest,
    MemoryForgetRequest,
    MemoryListRequest,
    MemoryRememberRequest,
    MemoryToggleRequest,
    ModelListRequest,
    ModelProviderUpsertRequest,
    ModelReloadRequest,
    ModelSelectRequest,
    PermissionsGetRequest,
    PermissionsSetRequest,
    PlanGetRequest,
    RuntimeStatusRequest,
    SessionCreateRequest,
    SessionDeleteRequest,
    SessionListRequest,
    SessionResumeRequest,
    SkillsListRequest,
    SkillsReloadRequest,
    SkillsToggleRequest,
    StepsGetRequest,
    StepsResetRequest,
    StepsSetRequest,
    TurnCancelRequest,
    TurnStartRequest,
    ViewEventType,
    parse_client_request,
)

_CSP = (
    "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
    "img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'"
)


def create_web_app(
    *,
    coordinator: TurnCoordinator,
    auth: LaunchAuth,
    static_dir: Path,
) -> FastAPI:
    index_path = static_dir / "index.html"
    if not index_path.is_file():
        raise FileNotFoundError(f"Web UI assets are missing: {index_path}")
    index_html = index_path.read_text(encoding="utf-8").replace(
        "__FORGE_PRODUCT_NAME__",
        html.escape(PRODUCT_NAME),
    )

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(index_html)

    @app.post("/api/bootstrap", status_code=204)
    async def bootstrap(request: Request) -> Response:
        token = auth.exchange(
            request.headers.get("x-forge-capability", ""),
            host=request.headers.get("host", ""),
            origin=request.headers.get("origin", ""),
        )
        if token is None:
            raise HTTPException(status_code=403, detail="invalid launch capability")
        response = Response(status_code=204)
        response.set_cookie(
            auth.cookie_name,
            token,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.websocket("/ws")
    async def event_socket(websocket: WebSocket) -> None:
        token = websocket.cookies.get(auth.cookie_name)
        host = websocket.headers.get("host", "")
        origin = websocket.headers.get("origin", "")
        if token is None or not auth.authorize(token, host=host, origin=origin):
            await websocket.close(code=4403)
            return
        if not auth.claim_controller(token):
            await websocket.close(code=4409)
            return

        await websocket.accept()
        sender = asyncio.create_task(_send_events(websocket, coordinator))
        try:
            while True:
                payload = await websocket.receive_json()
                try:
                    request = parse_client_request(payload)
                    _dispatch_request(coordinator, request)
                except (ValidationError, CoordinatorError, ValueError) as exc:
                    coordinator.emit(
                        ViewEventType.ERROR,
                        {
                            "severity": "error",
                            "message": str(exc),
                            "recoverable": True,
                        },
                    )
        except WebSocketDisconnect:
            pass
        finally:
            coordinator.disconnect()
            sender.cancel()
            with suppress(asyncio.CancelledError):
                await sender
            auth.release_controller(token)

    return app


async def _send_events(websocket: WebSocket, coordinator: TurnCoordinator) -> None:
    while True:
        event = await asyncio.to_thread(coordinator.next_event, 0.1)
        if event is not None:
            await websocket.send_json(event.model_dump(mode="json"))


def _dispatch_request(coordinator: TurnCoordinator, request: object) -> None:
    if isinstance(request, TurnStartRequest):
        coordinator.start_turn(request.task)
        return
    if isinstance(request, TurnCancelRequest):
        coordinator.cancel_turn()
        return
    if isinstance(request, SessionCreateRequest):
        coordinator.new_session()
        coordinator.publish_snapshot(replace_timeline=True)
        return
    if isinstance(request, SessionResumeRequest):
        session_id = coordinator.resume_session(request.session_id)
        coordinator.publish_snapshot(replace_timeline=True)
        coordinator.publish_history(session_id)
        return
    if isinstance(request, SessionDeleteRequest):
        delete_result = coordinator.delete_session(request.session_id)
        coordinator.publish_snapshot(
            replace_timeline=delete_result["replacement_session_id"] is not None
        )
        memory = delete_result.get("memory")
        if isinstance(memory, dict):
            coordinator.emit(ViewEventType.MEMORY_UPDATED, {"memory": memory})
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {
                "command": request.type,
                "status": "completed",
                "deleted_session_id": request.session_id,
                "deleted_memory_count": delete_result["deleted_memory_count"],
            },
        )
        return
    if isinstance(request, InitializeRequest):
        restored_session = coordinator.restore_startup_session()
        coordinator.publish_snapshot(replace_timeline=restored_session is not None)
        if restored_session is not None:
            coordinator.publish_history(restored_session)
        return
    if isinstance(request, SessionListRequest):
        coordinator.publish_snapshot()
        return
    if isinstance(request, ApprovalResolveRequest):
        if not coordinator.resolve_approval(request.approval_id, request.decision):
            coordinator.emit(
                ViewEventType.ERROR,
                {
                    "severity": "error",
                    "message": "no matching approval is pending",
                    "recoverable": True,
                },
            )
        return
    if isinstance(request, FilePreviewRequest):
        try:
            preview = coordinator.preview_file(request.path)
        except PreviewError as exc:
            coordinator.emit(
                ViewEventType.ERROR,
                {
                    "severity": "error",
                    "message": str(exc),
                    "code": exc.code,
                    "recoverable": True,
                },
            )
            return
        coordinator.emit(ViewEventType.FILE_PREVIEWED, preview)
        return
    if isinstance(request, ChangesListRequest):
        coordinator.emit(
            ViewEventType.CHANGES_UPDATED,
            {"changes": coordinator.list_changes()},
        )
        return
    if isinstance(request, ChangeUndoRequest):
        try:
            change = coordinator.undo_change(request.change_id)
        except (CoordinatorError, OSError, ValueError) as exc:
            message = str(exc)
            if "changed since this Diff was recorded" in message:
                message = "文件在该 Diff 之后已被修改，无法安全撤销。"
            elif "no longer available" in message:
                message = "这条 Diff 已撤销或不再可用。"
            coordinator.emit(
                ViewEventType.ERROR,
                {
                    "severity": "error",
                    "message": message,
                    "code": "CHANGE_UNDO_FAILED",
                    "recoverable": True,
                },
            )
            return
        coordinator.emit(
            ViewEventType.CHANGES_UPDATED,
            {"changes": coordinator.list_changes()},
        )
        coordinator.emit(
            ViewEventType.ACTIVITY_UPSERT,
            {
                "activity_id": f"undo:{request.change_id}",
                "kind": "file_change",
                "title": "撤销变更",
                "status": "completed",
                "summary": str(change["path"]),
            },
        )
        return
    if isinstance(request, ConfigGetRequest):
        coordinator.publish_snapshot()
        return
    if isinstance(request, (RuntimeStatusRequest, StepsGetRequest, PermissionsGetRequest)):
        snapshot = coordinator.runtime_status()
        coordinator.emit(
            ViewEventType.RUNTIME_UPDATED,
            {"runtime": snapshot.model_dump(mode="json")},
        )
        return
    if isinstance(request, PermissionsSetRequest):
        snapshot = coordinator.set_permissions(request.mode)
        coordinator.emit(
            ViewEventType.RUNTIME_UPDATED,
            {"runtime": snapshot.model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {"command": request.type, "status": "completed"},
        )
        return
    if isinstance(request, StepsSetRequest):
        snapshot = coordinator.set_steps(request.value)
        coordinator.emit(
            ViewEventType.RUNTIME_UPDATED,
            {"runtime": snapshot.model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {"command": request.type, "status": "completed"},
        )
        return
    if isinstance(request, StepsResetRequest):
        snapshot = coordinator.reset_steps()
        coordinator.emit(
            ViewEventType.RUNTIME_UPDATED,
            {"runtime": snapshot.model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {"command": request.type, "status": "completed"},
        )
        return
    if isinstance(request, PlanGetRequest):
        coordinator.emit(
            ViewEventType.PLAN_UPDATED,
            {
                "plan": [
                    item.model_dump(mode="json")
                    for item in coordinator.plan_snapshot()
                    if hasattr(item, "model_dump")
                ]
            },
        )
        return
    if isinstance(request, CompletionQueryRequest):
        items = coordinator.completion_query(request.text, request.cursor, request.limit)
        coordinator.emit(
            ViewEventType.COMPLETION_UPDATED,
            {
                "request_id": request.request_id,
                "text": request.text,
                "cursor": request.cursor,
                "items": [item.model_dump(mode="json") for item in items],
            },
        )
        return
    if isinstance(request, ModelListRequest):
        catalog = coordinator.model_catalog()
        coordinator.emit(
            ViewEventType.MODEL_CATALOG_UPDATED,
            {"catalog": catalog.model_dump(mode="json")},
        )
        return
    if isinstance(request, (ModelSelectRequest, ModelReloadRequest)):
        catalog = (
            coordinator.select_model(request.provider, request.model_id)
            if isinstance(request, ModelSelectRequest)
            else coordinator.reload_models()
        )
        coordinator.emit(
            ViewEventType.MODEL_CATALOG_UPDATED,
            {"catalog": catalog.model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.RUNTIME_UPDATED,
            {"runtime": coordinator.runtime_status().model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {"command": request.type, "status": "completed"},
        )
        return
    if isinstance(request, ModelProviderUpsertRequest):
        configured = coordinator.upsert_model_provider(
            provider=request.provider,
            base_url=request.base_url,
            model=request.model,
            compatibility=request.compatibility,
        )
        coordinator.emit(
            ViewEventType.MODEL_CATALOG_UPDATED,
            {"catalog": configured.catalog.model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {
                "command": request.type,
                "status": "completed",
                "provider": configured.provider,
                "model": configured.model,
                "api_key_env": configured.api_key_env,
                "requires_restart": True,
            },
        )
        return
    if isinstance(request, MemoryListRequest):
        memory = coordinator.memory_snapshot()
        coordinator.emit(
            ViewEventType.MEMORY_UPDATED,
            {"memory": memory.model_dump(mode="json")},
        )
        return
    if isinstance(
        request,
        (MemoryToggleRequest, MemoryRememberRequest, MemoryForgetRequest, MemoryClearRequest),
    ):
        if isinstance(request, MemoryToggleRequest):
            memory = coordinator.set_memory_enabled(request.enabled)
        elif isinstance(request, MemoryRememberRequest):
            memory = coordinator.remember(request.content)
        elif isinstance(request, MemoryForgetRequest):
            memory = coordinator.forget_memory(request.memory_id)
        else:
            memory = coordinator.clear_memory()
        coordinator.emit(
            ViewEventType.MEMORY_UPDATED,
            {"memory": memory.model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {"command": request.type, "status": "completed"},
        )
        return
    if isinstance(request, SkillsListRequest):
        skills = coordinator.skills_snapshot()
        coordinator.emit(
            ViewEventType.SKILLS_UPDATED,
            {"skills": skills.model_dump(mode="json")},
        )
        return
    if isinstance(request, (SkillsToggleRequest, SkillsReloadRequest)):
        skills = (
            coordinator.set_skill_enabled(request.name, request.enabled)
            if isinstance(request, SkillsToggleRequest)
            else coordinator.reload_skills()
        )
        coordinator.emit(
            ViewEventType.SKILLS_UPDATED,
            {"skills": skills.model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {"command": request.type, "status": "completed"},
        )
        return
    if isinstance(request, ContextGetRequest):
        coordinator.emit(
            ViewEventType.RUNTIME_UPDATED,
            {"runtime": coordinator.runtime_status().model_dump(mode="json")},
        )
        return
    if isinstance(request, ContextCompactRequest):
        result = coordinator.compact_context()
        coordinator.emit(
            ViewEventType.CONTEXT_COMPACTED,
            {"result": result.model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.RUNTIME_UPDATED,
            {"runtime": coordinator.runtime_status().model_dump(mode="json")},
        )
        coordinator.emit(
            ViewEventType.COMMAND_COMPLETED,
            {"command": request.type, "status": "completed"},
        )
        return
    coordinator.emit(
        ViewEventType.ERROR,
        {"severity": "error", "message": "request is not available yet", "recoverable": True},
    )
