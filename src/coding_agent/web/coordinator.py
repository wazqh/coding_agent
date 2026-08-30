from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Protocol, cast

from coding_agent.controller import RunResult
from coding_agent.events import AgentEvent, EventKind
from coding_agent.memory import MemoryStore
from coding_agent.runtime_management import (
    CompactResult,
    LifecycleState,
    MemorySnapshot,
    ModelCatalogSnapshot,
    ProviderConfigurationResult,
    RuntimeManagement,
    RuntimeSnapshot,
    SkillsSnapshot,
)
from coding_agent.safety.approval import ApprovalDecision, ApprovalRequest
from coding_agent.safety.paths import WorkspacePaths
from coding_agent.session import SessionStore
from coding_agent.tools.base import AppliedChange, WorkingState
from coding_agent.tools.filesystem import undo_change as undo_file_change
from coding_agent.web.approval import ApprovalBroker
from coding_agent.web.changes import legacy_diff_path, summarize_diff
from coding_agent.web.completion import CompletionItem, query_completions
from coding_agent.web.presenter import AgentEventPresenter
from coding_agent.web.preview import WorkspacePreview
from coding_agent.web.protocol import ViewEvent, ViewEventType


class CoordinatorError(RuntimeError):
    pass


class CoordinatorBusyError(CoordinatorError):
    pass


class _Controller(Protocol):
    session_id: str

    @property
    def working(self) -> _Working: ...

    def run_turn(self, task: str, *, cancel_event: Event | None = None) -> RunResult: ...


class _Runtime(Protocol):
    def create(self, session_id: str | None = None) -> _Controller: ...


class _Working(Protocol):
    diffs: list[str]
    changes: list[AppliedChange]


class TurnCoordinator:
    """Run one synchronous controller turn without blocking the UI event loop."""

    def __init__(self) -> None:
        self._runtime: _Runtime | None = None
        self._controller: _Controller | None = None
        self._presenter = AgentEventPresenter()
        self._events: Queue[ViewEvent] = Queue()
        self._lock = Lock()
        self._event_lock = Lock()
        self._thread: Thread | None = None
        self._cancel_event: Event | None = None
        self._approval_broker: ApprovalBroker | None = None
        self._next_approval_context: tuple[str, str | None] | None = None
        self._approval_contexts: dict[str, tuple[str, str | None]] = {}
        self._runtime_metadata: dict[str, object] = {}
        self._management: RuntimeManagement | None = None
        self._workspace: Path | None = None
        self._sessions: SessionStore | None = None
        self._memory: MemoryStore | None = None
        self._preview: WorkspacePreview | None = None
        self._idle = Event()
        self._idle.set()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._thread is not None

    @property
    def session_id(self) -> str | None:
        with self._lock:
            return self._controller.session_id if self._controller is not None else None

    def attach_runtime(self, runtime: _Runtime) -> None:
        with self._lock:
            if self._runtime is not None:
                raise CoordinatorError("runtime is already attached")
            self._runtime = runtime

    def attach_approval_broker(self, broker: ApprovalBroker) -> None:
        with self._lock:
            if self._approval_broker is not None:
                raise CoordinatorError("approval broker is already attached")
            self._approval_broker = broker

    def attach_management(self, management: RuntimeManagement) -> None:
        with self._lock:
            if self._management is not None:
                raise CoordinatorError("runtime management is already attached")
            self._management = management

    def configure_runtime_metadata(
        self,
        *,
        workspace_name: str,
        workspace_path: str,
        model: str,
        permissions: str,
        context_window: int,
    ) -> None:
        """Publish non-secret runtime identity in the initial UI snapshot."""
        with self._lock:
            self._runtime_metadata = {
                "workspace_name": workspace_name,
                "workspace_path": workspace_path,
                "model": model,
                "permissions": permissions,
                "context_window": context_window,
            }

    def configure_workspace_services(
        self,
        *,
        workspace: Path,
        sessions: SessionStore,
        memory: MemoryStore | None = None,
    ) -> None:
        """Attach bounded workspace/session projections used by the graphical frontend."""

        resolved = workspace.resolve(strict=True)
        with self._lock:
            self._workspace = resolved
            self._sessions = sessions
            self._memory = memory or MemoryStore(
                data_dir=sessions.directory.parent,
                workspace=resolved,
                enabled=False,
            )
            self._preview = WorkspacePreview(resolved)

    def _require_runtime(self) -> _Runtime:
        if self._runtime is None:
            raise CoordinatorError("runtime is not attached")
        return self._runtime

    def _ensure_controller(self) -> _Controller:
        if self._controller is None:
            self._controller = self._require_runtime().create()
        return self._controller

    def controller(self) -> _Controller:
        with self._lock:
            return self._ensure_controller()

    def _require_management(self) -> RuntimeManagement:
        with self._lock:
            if self._management is None:
                raise CoordinatorError("runtime management is not attached")
            return self._management

    def _require_idle_management(self) -> RuntimeManagement:
        with self._lock:
            if self._thread is not None:
                raise CoordinatorBusyError("cannot change runtime settings while a turn is running")
            if self._management is None:
                raise CoordinatorError("runtime management is not attached")
            return self._management

    def runtime_status(self) -> RuntimeSnapshot:
        return self._require_management().snapshot()

    def set_permissions(self, mode: str) -> RuntimeSnapshot:
        return self._require_idle_management().set_permissions(mode)

    def set_steps(self, value: int) -> RuntimeSnapshot:
        return self._require_idle_management().set_steps(value)

    def reset_steps(self) -> RuntimeSnapshot:
        return self._require_idle_management().reset_steps()

    def plan_snapshot(self) -> tuple[object, ...]:
        return tuple(self._require_management().snapshot().plan)

    def model_catalog(self) -> ModelCatalogSnapshot:
        return self._require_management().model_catalog()

    def select_model(self, provider: str, model_id: str | None) -> ModelCatalogSnapshot:
        return self._require_idle_management().select_model(provider, model_id)

    def reload_models(self) -> ModelCatalogSnapshot:
        return self._require_idle_management().reload_models()

    def upsert_model_provider(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        compatibility: str,
    ) -> ProviderConfigurationResult:
        return self._require_idle_management().upsert_model_provider(
            provider=provider,
            base_url=base_url,
            model=model,
            compatibility=compatibility,  # type: ignore[arg-type]
        )

    def memory_snapshot(self) -> MemorySnapshot:
        return self._require_management().memory_snapshot()

    def set_memory_enabled(self, enabled: bool) -> MemorySnapshot:
        return self._require_idle_management().set_memory_enabled(enabled)

    def remember(self, content: str) -> MemorySnapshot:
        return self._require_idle_management().remember(content)

    def forget_memory(self, memory_id: str) -> MemorySnapshot:
        return self._require_idle_management().forget_memory(memory_id)

    def clear_memory(self) -> MemorySnapshot:
        return self._require_idle_management().clear_memory()

    def skills_snapshot(self) -> SkillsSnapshot:
        return self._require_management().skills_snapshot()

    def set_skill_enabled(self, name: str, enabled: bool) -> SkillsSnapshot:
        return self._require_idle_management().set_skill_enabled(name, enabled)

    def reload_skills(self) -> SkillsSnapshot:
        return self._require_idle_management().reload_skills()

    def compact_context(self) -> CompactResult:
        return self._require_idle_management().compact_context()

    def completion_query(self, text: str, cursor: int, limit: int) -> list[CompletionItem]:
        with self._lock:
            workspace = self._workspace
            runtime = self._runtime
        if workspace is None:
            raise CoordinatorError("workspace completion is unavailable")
        controller = self.controller()
        return query_completions(
            text=text,
            cursor=cursor,
            workspace=workspace,
            skills_provider=lambda: getattr(controller, "skills", None),
            model_catalog=getattr(runtime, "catalog", None),
            limit=limit,
        )

    def _publish(
        self,
        *,
        session_id: str,
        kind: ViewEventType,
        data: dict[str, object],
        turn_id: str | None = None,
    ) -> None:
        with self._event_lock:
            self._events.put(
                self._presenter.create_view(
                    session_id=session_id,
                    turn_id=turn_id,
                    kind=kind,
                    data=data,
                )
            )

    def new_session(self) -> str:
        with self._lock:
            if self._thread is not None:
                raise CoordinatorBusyError("cannot switch sessions while a turn is running")
            self._controller = self._require_runtime().create()
            return self._controller.session_id

    def restore_startup_session(self) -> str | None:
        """Restore the most recent useful session for this workspace on first initialize."""

        with self._lock:
            if self._controller is not None:
                return None
            if self._sessions is None or self._workspace is None:
                return None
            candidates = self._workspace_sessions(self._sessions, self._workspace)
            if not candidates:
                return None
            selected = next(
                (item for item in candidates if str(item.get("title", "")).strip()),
                candidates[0],
            )
            session_id = str(selected["id"])
            self._controller = self._require_runtime().create(session_id)
            return self._controller.session_id

    def resume_session(self, session_id: str) -> str:
        with self._lock:
            if self._thread is not None:
                raise CoordinatorBusyError("cannot switch sessions while a turn is running")
            if self._sessions is not None and self._workspace is not None:
                allowed = {
                    str(item["id"])
                    for item in self._workspace_sessions(self._sessions, self._workspace)
                }
                if session_id not in allowed:
                    raise CoordinatorError("session does not belong to the current workspace")
            self._controller = self._require_runtime().create(session_id)
            return self._controller.session_id

    def delete_session(self, session_id: str) -> dict[str, object]:
        """Delete a workspace session and only the memories evidenced by that session."""

        with self._lock:
            if self._thread is not None:
                raise CoordinatorBusyError("cannot delete sessions while a turn is running")
            if self._sessions is None or self._workspace is None:
                raise CoordinatorError("session storage is unavailable")
            allowed = {
                str(item["id"])
                for item in self._workspace_sessions(self._sessions, self._workspace)
            }
            if session_id not in allowed:
                raise CoordinatorError("session does not belong to the current workspace")
            sessions = self._sessions
            memory = self._memory
            active = self._controller is not None and self._controller.session_id == session_id

            replacement = None
            if active:
                try:
                    replacement = self._require_runtime().create()
                except Exception as exc:
                    raise CoordinatorError(f"could not create replacement session: {exc}") from exc

            def discard_replacement() -> None:
                if replacement is None or replacement.session_id == session_id:
                    return
                with suppress(OSError, ValueError):
                    sessions.delete(replacement.session_id)

            try:
                payload = sessions.delete(session_id)
            except (OSError, ValueError) as exc:
                discard_replacement()
                raise CoordinatorError(f"could not delete session: {exc}") from exc
            try:
                deleted_memory_count = 0 if memory is None else memory.delete_by_session(session_id)
            except (OSError, ValueError) as exc:
                try:
                    sessions.restore(session_id, payload)
                except (OSError, ValueError) as rollback_exc:
                    discard_replacement()
                    raise CoordinatorError(
                        f"could not delete session memory and rollback failed: {rollback_exc}"
                    ) from exc
                discard_replacement()
                raise CoordinatorError(f"could not delete session memory: {exc}") from exc

            replacement_session_id: str | None = None
            if replacement is not None:
                self._controller = replacement
                replacement_session_id = replacement.session_id

            memory_snapshot = None
            if memory is not None:
                memory_snapshot = {
                    "enabled": memory.enabled,
                    "items": [
                        item.model_dump(mode="json") for item in memory.list(include_disabled=True)
                    ],
                }
            return {
                "deleted_session_id": session_id,
                "deleted_memory_count": deleted_memory_count,
                "replacement_session_id": replacement_session_id,
                "memory": memory_snapshot,
            }

    def start_turn(self, task: str) -> str:
        with self._lock:
            if self._thread is not None:
                raise CoordinatorBusyError("a turn is already running")
            controller = self._ensure_controller()
            cancel_event = Event()
            self._cancel_event = cancel_event
            self._idle.clear()
            management = self._management
            if management is not None:
                management.set_lifecycle(LifecycleState.REQUESTING)
            self._publish(
                session_id=controller.session_id,
                kind=ViewEventType.TURN_STARTED,
                data={"task": task},
            )
            thread = Thread(
                target=self._run_turn,
                args=(controller, task, cancel_event),
                name="forge-web-turn",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return controller.session_id

    def _run_turn(self, controller: _Controller, task: str, cancel_event: Event) -> None:
        try:
            controller.run_turn(task, cancel_event=cancel_event)
        except Exception as exc:
            with self._lock:
                management = self._management
            if management is not None:
                management.set_lifecycle(LifecycleState.FAILED)
            self._publish(
                session_id=controller.session_id,
                kind=ViewEventType.ERROR,
                data={"severity": "error", "message": f"{type(exc).__name__}: {exc}"},
            )
            self._publish(
                session_id=controller.session_id,
                kind=ViewEventType.TURN_FINISHED,
                data={"status": "failed", "reason": "internal error"},
            )
        finally:
            with self._lock:
                self._thread = None
                self._cancel_event = None
                self._idle.set()

    def cancel_turn(self) -> bool:
        with self._lock:
            if self._cancel_event is None:
                return False
            self._cancel_event.set()
            broker = self._approval_broker
        cancelled_ids = broker.cancel_pending() if broker is not None else ()
        for approval_id in cancelled_ids:
            with self._lock:
                context = self._approval_contexts.pop(approval_id, None)
            if context is not None:
                session_id, turn_id = context
                self._publish(
                    session_id=session_id,
                    turn_id=turn_id,
                    kind=ViewEventType.APPROVAL_RESOLVED,
                    data={"approval_id": approval_id, "decision": "cancelled"},
                )
        return True

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def handle_agent_event(self, event: AgentEvent) -> None:
        with self._lock:
            management = self._management
        if management is not None and event.state is not None:
            state_map = {
                "awaiting_approval": LifecycleState.AWAITING_APPROVAL,
                "tool_pending": LifecycleState.EXECUTING_TOOL,
                "executing": LifecycleState.EXECUTING_TOOL,
                "completed": LifecycleState.COMPLETED,
                "cancelled": LifecycleState.CANCELLED,
                "failed": LifecycleState.FAILED,
                "thinking": LifecycleState.REQUESTING,
                "planning": LifecycleState.REQUESTING,
                "observing": LifecycleState.REQUESTING,
            }
            lifecycle = state_map.get(event.state.value)
            if lifecycle is not None:
                management.set_lifecycle(lifecycle)
        if event.kind is EventKind.APPROVAL:
            if "request" in event.data:
                with self._lock:
                    self._next_approval_context = (event.session_id, event.turn_id)
            return
        with self._event_lock:
            for presented in self._presenter.present(event):
                self._events.put(presented)

    def publish_approval(self, approval_id: str, request: ApprovalRequest) -> None:
        with self._lock:
            context = self._next_approval_context
        if context is None:
            session_id = self.session_id
            if session_id is None:
                raise CoordinatorError("approval has no active session")
            context = (session_id, None)
        with self._lock:
            self._approval_contexts[approval_id] = context
            if self._next_approval_context == context:
                self._next_approval_context = None
        session_id, turn_id = context
        self._publish(
            session_id=session_id,
            turn_id=turn_id,
            kind=ViewEventType.APPROVAL_REQUESTED,
            data={
                "approval_id": approval_id,
                "request": request.model_dump(mode="json"),
            },
        )

    def resolve_approval(self, approval_id: str, decision: ApprovalDecision) -> bool:
        with self._lock:
            broker = self._approval_broker
        if broker is None or not broker.resolve(approval_id, decision):
            return False
        with self._lock:
            context = self._approval_contexts.pop(approval_id, None)
        if context is not None:
            session_id, turn_id = context
            self._publish(
                session_id=session_id,
                turn_id=turn_id,
                kind=ViewEventType.APPROVAL_RESOLVED,
                data={"approval_id": approval_id, "decision": decision.value},
            )
        return True

    def emit(
        self,
        kind: ViewEventType,
        data: dict[str, object],
        *,
        session_id: str | None = None,
    ) -> None:
        effective_session = session_id or self.session_id
        if effective_session is None:
            effective_session = self.new_session()
        self._publish(session_id=effective_session, kind=kind, data=data)

    def publish_snapshot(self, *, replace_timeline: bool = False) -> str:
        session_id = self.session_id or self.new_session()
        data = self.snapshot()
        data["replace_timeline"] = replace_timeline
        self._publish(session_id=session_id, kind=ViewEventType.SNAPSHOT, data=data)
        return session_id

    def publish_history(self, session_id: str) -> None:
        with self._lock:
            sessions = self._sessions
        if sessions is None:
            raise CoordinatorError("session history is unavailable")
        records = sessions.replay(session_id)
        with self._event_lock:
            for event in self._presenter.present_history(session_id, records):
                self._events.put(event)

    def preview_file(self, path: str) -> dict[str, object]:
        with self._lock:
            preview = self._preview
        if preview is None:
            raise CoordinatorError("workspace preview is unavailable")
        return preview.read(path)

    def list_changes(self) -> list[dict[str, object]]:
        with self._lock:
            controller = self._controller
            diffs = list(controller.working.diffs) if controller is not None else []
            recorded = list(getattr(controller.working, "changes", [])) if controller else []
        if recorded:
            return [
                {
                    **summarize_diff(
                        change_id=change.id,
                        path=change.path,
                        kind=change.kind,
                        diff=change.diff,
                    ),
                    "reversible": change.reversible,
                }
                for change in recorded
            ]
        changes: list[dict[str, object]] = []
        for index, diff in enumerate(diffs, start=1):
            summary = summarize_diff(
                change_id=f"change-{index}",
                path=legacy_diff_path(diff),
                kind="modified",
                diff=diff,
            )
            summary.pop("kind", None)
            changes.append(summary)
        return changes

    def undo_change(self, change_id: str) -> dict[str, object]:
        with self._lock:
            if self._thread is not None:
                raise CoordinatorBusyError("cannot undo while a turn is running")
            controller = self._controller
            workspace = self._workspace
        if controller is None or workspace is None:
            raise CoordinatorError("change history is unavailable")
        change = undo_file_change(
            cast(WorkingState, controller.working),
            WorkspacePaths(workspace),
            change_id,
        )
        return summarize_diff(
            change_id=change.id,
            path=change.path,
            kind=change.kind,
            diff=change.diff,
        )

    @staticmethod
    def _workspace_sessions(sessions: SessionStore, workspace: Path) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for item in sessions.list():
            raw_workspace = item.get("workspace")
            if not raw_workspace:
                continue
            try:
                item_workspace = Path(str(raw_workspace)).resolve()
            except (OSError, ValueError):
                continue
            if item_workspace == workspace:
                result.append(item)
        return result

    @staticmethod
    def _project_sessions(
        sessions: SessionStore,
        current_workspace: Path,
    ) -> list[dict[str, object]]:
        current = current_workspace.resolve()
        grouped: dict[Path, list[dict[str, object]]] = {}
        for item in sessions.list():
            raw_workspace = item.get("workspace")
            if not raw_workspace:
                continue
            try:
                workspace = Path(str(raw_workspace)).resolve()
            except (OSError, ValueError):
                continue
            grouped.setdefault(workspace, []).append(item)
        ordered = sorted(
            grouped.items(),
            key=lambda entry: (entry[0] != current, -len(entry[1]), str(entry[0]).casefold()),
        )
        return [
            {
                "name": workspace.name or str(workspace),
                "path": str(workspace),
                "current": workspace == current,
                "sessions": project_sessions,
            }
            for workspace, project_sessions in ordered
        ]

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            management = self._management
            snapshot = {
                "session_id": (
                    self._controller.session_id if self._controller is not None else None
                ),
                "busy": self._thread is not None,
                **self._runtime_metadata,
            }
            sessions = self._sessions
            workspace = self._workspace
        if management is not None:
            runtime = management.snapshot()
            snapshot.update(
                {
                    "session_id": runtime.session_id,
                    "workspace_name": runtime.workspace_name,
                    "workspace_path": runtime.workspace,
                    "model": runtime.model.id,
                    "permissions": runtime.permissions,
                    "context_window": runtime.context.context_window,
                    "runtime": runtime.model_dump(mode="json"),
                }
            )
        if sessions is not None and workspace is not None:
            snapshot["sessions"] = self._workspace_sessions(sessions, workspace)
            snapshot["projects"] = self._project_sessions(sessions, workspace)
        return snapshot

    def next_event(self, timeout: float | None = None) -> ViewEvent | None:
        try:
            return self._events.get(timeout=timeout)
        except Empty:
            return None

    def drain_events(self) -> list[ViewEvent]:
        events: list[ViewEvent] = []
        while True:
            event = self.next_event(timeout=0)
            if event is None:
                return events
            events.append(event)

    def disconnect(self, cancel_approvals: Callable[[], object] | None = None) -> None:
        self.cancel_turn()
        with self._lock:
            broker = self._approval_broker
        if broker is not None:
            broker.cancel_all()
        elif cancel_approvals is not None:
            cancel_approvals()
