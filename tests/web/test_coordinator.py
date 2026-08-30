from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from coding_agent.controller import RunResult
from coding_agent.events import AgentEvent, AgentState, EventKind
from coding_agent.safety.approval import ApprovalDecision, ApprovalRequest
from coding_agent.session import SessionStore
from coding_agent.web.approval import ApprovalBroker
from coding_agent.web.coordinator import CoordinatorBusyError, CoordinatorError, TurnCoordinator
from coding_agent.web.protocol import ViewEventType

SESSION_ID = "b" * 24


class FakeController:
    def __init__(
        self,
        event_sink: Callable[[AgentEvent], None],
        *,
        release: Event | None = None,
        session_id: str = SESSION_ID,
    ) -> None:
        self.event_sink = event_sink
        self.release = release
        self.session_id = session_id
        self.working = SimpleNamespace(diffs=[])

    def run_turn(self, task: str, *, cancel_event: Event | None = None) -> RunResult:
        turn_id = "turn-1"
        self.event_sink(
            AgentEvent(
                kind=EventKind.TEXT,
                session_id=self.session_id,
                turn_id=turn_id,
                data={"delta": f"answer:{task}"},
            )
        )
        if self.release is not None:
            while not self.release.wait(0.01):
                if cancel_event is not None and cancel_event.is_set():
                    break
        status = (
            AgentState.CANCELLED
            if cancel_event is not None and cancel_event.is_set()
            else AgentState.COMPLETED
        )
        self.event_sink(
            AgentEvent(
                kind=EventKind.DONE,
                session_id=self.session_id,
                turn_id=turn_id,
                state=status,
                data={"reason": status.value, "exit_code": 0, "tool_steps": 0},
            )
        )
        return RunResult(status, 0, self.session_id, f"answer:{task}", 0, status.value)


class FakeRuntime:
    def __init__(
        self, event_sink: Callable[[AgentEvent], None], release: Event | None = None
    ) -> None:
        self.event_sink = event_sink
        self.release = release
        self.created: list[str | None] = []
        self.controllers: list[FakeController] = []

    def create(self, session_id: str | None = None) -> FakeController:
        self.created.append(session_id)
        controller = FakeController(
            self.event_sink,
            release=self.release,
            session_id=session_id or SESSION_ID,
        )
        self.controllers.append(controller)
        return controller


class WaitingApprovalController(FakeController):
    def __init__(
        self,
        event_sink: Callable[[AgentEvent], None],
        broker: ApprovalBroker,
    ) -> None:
        super().__init__(event_sink)
        self.broker = broker

    def run_turn(self, task: str, *, cancel_event: Event | None = None) -> RunResult:
        turn_id = "turn-approval"
        request = ApprovalRequest(
            action="run_command",
            subject="pytest -q",
            summary="run tests",
        )
        self.event_sink(
            AgentEvent(
                kind=EventKind.APPROVAL,
                session_id=self.session_id,
                turn_id=turn_id,
                state=AgentState.AWAITING_APPROVAL,
                data={"request": request.model_dump(mode="json")},
            )
        )
        self.broker.request(request)
        status = (
            AgentState.CANCELLED if cancel_event and cancel_event.is_set() else AgentState.FAILED
        )
        self.event_sink(
            AgentEvent(
                kind=EventKind.DONE,
                session_id=self.session_id,
                turn_id=turn_id,
                state=status,
                data={"reason": status.value, "exit_code": 0, "tool_steps": 0},
            )
        )
        return RunResult(status, 0, self.session_id, "", 0, status.value)


class WaitingApprovalRuntime:
    def __init__(
        self,
        event_sink: Callable[[AgentEvent], None],
        broker: ApprovalBroker,
    ) -> None:
        self.event_sink = event_sink
        self.broker = broker

    def create(self, session_id: str | None = None) -> WaitingApprovalController:
        return WaitingApprovalController(self.event_sink, self.broker)


def test_snapshot_includes_frontend_runtime_metadata() -> None:
    coordinator = TurnCoordinator()
    coordinator.configure_runtime_metadata(
        workspace_name="coding_agent",
        workspace_path=r"D:\codes\coding_agent",
        model="gemini-flash",
        permissions="prompt",
        context_window=128_000,
    )

    assert coordinator.snapshot() == {
        "session_id": None,
        "busy": False,
        "workspace_name": "coding_agent",
        "workspace_path": r"D:\codes\coding_agent",
        "model": "gemini-flash",
        "permissions": "prompt",
        "context_window": 128_000,
    }


def test_coordinator_streams_ordered_semantic_events() -> None:
    coordinator = TurnCoordinator()
    runtime = FakeRuntime(coordinator.handle_agent_event)
    coordinator.attach_runtime(runtime)

    coordinator.start_turn("hello")
    assert coordinator.wait_until_idle(timeout=1)
    events = coordinator.drain_events()

    assert [event.type for event in events] == [
        ViewEventType.TURN_STARTED,
        ViewEventType.MESSAGE_DELTA,
        ViewEventType.TURN_FINISHED,
    ]
    assert [event.seq for event in events] == [1, 2, 3]
    assert events[1].data["delta"] == "answer:hello"
    assert runtime.created == [None]


def test_coordinator_rejects_parallel_turn_and_cancels_active_work() -> None:
    release = Event()
    coordinator = TurnCoordinator()
    coordinator.attach_runtime(FakeRuntime(coordinator.handle_agent_event, release=release))
    coordinator.start_turn("long task")

    with pytest.raises(CoordinatorBusyError):
        coordinator.start_turn("second task")

    assert coordinator.cancel_turn() is True
    assert coordinator.wait_until_idle(timeout=1)
    assert coordinator.cancel_turn() is False
    assert coordinator.drain_events()[-1].data["status"] == "cancelled"


def test_coordinator_prevents_session_switch_while_busy() -> None:
    release = Event()
    coordinator = TurnCoordinator()
    runtime = FakeRuntime(coordinator.handle_agent_event, release=release)
    coordinator.attach_runtime(runtime)
    coordinator.start_turn("long task")

    with pytest.raises(CoordinatorBusyError):
        coordinator.resume_session("c" * 24)

    coordinator.cancel_turn()
    assert coordinator.wait_until_idle(timeout=1)
    coordinator.resume_session("c" * 24)
    assert runtime.created == [None, "c" * 24]


def test_management_mutation_is_rejected_while_turn_is_busy() -> None:
    release = Event()
    coordinator = TurnCoordinator()
    coordinator.attach_runtime(FakeRuntime(coordinator.handle_agent_event, release=release))
    management = SimpleNamespace(
        set_permissions=lambda mode: mode,
        set_lifecycle=lambda lifecycle: lifecycle,
    )
    coordinator.attach_management(management)
    coordinator.start_turn("long task")

    with pytest.raises(CoordinatorBusyError, match="turn is running"):
        coordinator.set_permissions("auto")

    coordinator.cancel_turn()
    assert coordinator.wait_until_idle(timeout=1)


def test_coordinator_attaches_opaque_id_to_approval_round_trip() -> None:
    coordinator = TurnCoordinator()
    coordinator.attach_runtime(FakeRuntime(coordinator.handle_agent_event))
    request = ApprovalRequest(
        action="run_command",
        subject="pytest -q",
        summary="run tests",
    )
    broker = ApprovalBroker(on_request=coordinator.publish_approval)
    coordinator.attach_approval_broker(broker)
    coordinator.handle_agent_event(
        AgentEvent(
            kind=EventKind.APPROVAL,
            session_id=SESSION_ID,
            turn_id="turn-approval",
            state=AgentState.AWAITING_APPROVAL,
            data={"request": request.model_dump(mode="json")},
        )
    )
    result: Queue[ApprovalDecision] = Queue()
    worker = Thread(target=lambda: result.put(broker.request(request)))
    worker.start()

    requested = coordinator.next_event(timeout=1)
    assert requested is not None
    approval_id = requested.data["approval_id"]
    assert isinstance(approval_id, str)
    assert requested.type is ViewEventType.APPROVAL_REQUESTED
    assert requested.turn_id == "turn-approval"

    assert coordinator.resolve_approval(approval_id, ApprovalDecision.ALLOW_ONCE)
    worker.join(timeout=1)
    resolved = coordinator.next_event(timeout=1)
    assert resolved is not None
    assert resolved.type is ViewEventType.APPROVAL_RESOLVED
    assert resolved.data == {"approval_id": approval_id, "decision": "allow_once"}
    assert result.get_nowait() is ApprovalDecision.ALLOW_ONCE


def test_consecutive_approvals_keep_their_own_resolution_contexts() -> None:
    first_resolve_released_worker = Event()
    allow_first_resolve_to_return = Event()

    class YieldingApprovalBroker(ApprovalBroker):
        def resolve(self, approval_id: str, decision: ApprovalDecision) -> bool:
            resolved = super().resolve(approval_id, decision)
            if resolved and not first_resolve_released_worker.is_set():
                first_resolve_released_worker.set()
                assert allow_first_resolve_to_return.wait(timeout=1)
            return resolved

    coordinator = TurnCoordinator()
    coordinator.attach_runtime(FakeRuntime(coordinator.handle_agent_event))
    broker = YieldingApprovalBroker(on_request=coordinator.publish_approval)
    coordinator.attach_approval_broker(broker)
    decisions: Queue[ApprovalDecision] = Queue()

    def request_twice() -> None:
        for index in (1, 2):
            request = ApprovalRequest(
                action="run_command",
                subject=f"command-{index}",
                summary=f"run command {index}",
            )
            coordinator.handle_agent_event(
                AgentEvent(
                    kind=EventKind.APPROVAL,
                    session_id=SESSION_ID,
                    turn_id=f"turn-{index}",
                    state=AgentState.AWAITING_APPROVAL,
                    data={"request": request.model_dump(mode="json")},
                )
            )
            decisions.put(broker.request(request))

    worker = Thread(target=request_twice)
    worker.start()
    first_requested = coordinator.next_event(timeout=1)
    assert first_requested is not None
    first_id = str(first_requested.data["approval_id"])

    first_resolver = Thread(
        target=lambda: coordinator.resolve_approval(first_id, ApprovalDecision.ALLOW_ONCE)
    )
    first_resolver.start()
    assert first_resolve_released_worker.wait(timeout=1)
    second_requested = coordinator.next_event(timeout=1)
    assert second_requested is not None
    second_id = str(second_requested.data["approval_id"])

    allow_first_resolve_to_return.set()
    first_resolver.join(timeout=1)
    assert coordinator.resolve_approval(second_id, ApprovalDecision.DENY)
    worker.join(timeout=1)

    resolved_events = [
        event
        for event in coordinator.drain_events()
        if event.type is ViewEventType.APPROVAL_RESOLVED
    ]
    assert [(event.data["approval_id"], event.turn_id) for event in resolved_events] == [
        (first_id, "turn-1"),
        (second_id, "turn-2"),
    ]
    assert [decisions.get_nowait(), decisions.get_nowait()] == [
        ApprovalDecision.ALLOW_ONCE,
        ApprovalDecision.DENY,
    ]


def test_cancel_releases_a_turn_waiting_for_approval() -> None:
    coordinator = TurnCoordinator()
    broker = ApprovalBroker(on_request=coordinator.publish_approval)
    coordinator.attach_approval_broker(broker)
    coordinator.attach_runtime(WaitingApprovalRuntime(coordinator.handle_agent_event, broker))

    coordinator.start_turn("run tests")
    started = coordinator.next_event(timeout=1)
    requested = coordinator.next_event(timeout=1)
    assert started is not None and started.type is ViewEventType.TURN_STARTED
    assert requested is not None and requested.type is ViewEventType.APPROVAL_REQUESTED

    assert coordinator.cancel_turn() is True
    assert coordinator.wait_until_idle(timeout=1) is True
    events = coordinator.drain_events()

    resolved = next(event for event in events if event.type is ViewEventType.APPROVAL_RESOLVED)
    finished = next(event for event in events if event.type is ViewEventType.TURN_FINISHED)
    assert resolved.data["decision"] == "cancelled"
    assert finished.data["status"] == "cancelled"
    assert broker.pending_ids == ()


def test_concurrent_events_keep_sequence_and_queue_order_identical() -> None:
    coordinator = TurnCoordinator()

    def publish(worker: int) -> None:
        for index in range(50):
            coordinator.emit(
                ViewEventType.ERROR,
                {"severity": "warning", "message": f"{worker}:{index}"},
                session_id=SESSION_ID,
            )

    workers = [Thread(target=publish, args=(worker,)) for worker in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=2)

    events = coordinator.drain_events()
    assert len(events) == 200
    assert [event.seq for event in events] == list(range(1, 201))


def test_workspace_services_filter_sessions_and_restore_final_history(tmp_path: Path) -> None:
    sessions = SessionStore(tmp_path / "data")
    current = sessions.create({"workspace": str(tmp_path)})
    sessions.append_message(current, {"role": "user", "content": "修复测试"})
    sessions.append(
        current,
        "event",
        AgentEvent(
            kind=EventKind.TEXT,
            session_id=current,
            turn_id="turn-old",
            data={"delta": "duplicate"},
        ).model_dump(mode="json"),
    )
    sessions.append_message(current, {"role": "assistant", "content": "已经修复。"})
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    foreign = sessions.create({"workspace": str(other_workspace)})
    sessions.append_message(foreign, {"role": "user", "content": "整理其他项目"})

    coordinator = TurnCoordinator()
    coordinator.attach_runtime(FakeRuntime(coordinator.handle_agent_event))
    coordinator.configure_workspace_services(workspace=tmp_path, sessions=sessions)

    assert [item["id"] for item in coordinator.snapshot()["sessions"]] == [current]
    assert coordinator.snapshot()["projects"] == [
        {
            "name": tmp_path.name,
            "path": str(tmp_path.resolve()),
            "current": True,
            "sessions": [coordinator.snapshot()["sessions"][0]],
        },
        {
            "name": "other",
            "path": str(other_workspace.resolve()),
            "current": False,
            "sessions": [next(item for item in sessions.list() if item["id"] == foreign)],
        },
    ]
    coordinator.resume_session(current)
    coordinator.publish_snapshot(replace_timeline=True)
    coordinator.publish_history(current)
    events = coordinator.drain_events()

    assert events[0].type is ViewEventType.SNAPSHOT
    assert events[0].data["replace_timeline"] is True
    assert [event.data.get("content") for event in events[1:]] == ["修复测试", "已经修复。"]


def test_resume_rejects_session_from_another_workspace(tmp_path: Path) -> None:
    sessions = SessionStore(tmp_path / "data")
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    foreign = sessions.create({"workspace": str(other_workspace)})
    coordinator = TurnCoordinator()
    runtime = FakeRuntime(coordinator.handle_agent_event)
    coordinator.attach_runtime(runtime)
    coordinator.configure_workspace_services(workspace=tmp_path, sessions=sessions)

    with pytest.raises(CoordinatorError, match="current workspace"):
        coordinator.resume_session(foreign)

    assert runtime.created == []


def test_deleted_file_change_uses_the_workspace_path_not_dev_null(tmp_path: Path) -> None:
    coordinator = TurnCoordinator()
    runtime = FakeRuntime(coordinator.handle_agent_event)
    coordinator.attach_runtime(runtime)
    coordinator.configure_workspace_services(
        workspace=tmp_path,
        sessions=SessionStore(tmp_path / "data"),
    )
    coordinator.new_session()
    runtime.controllers[-1].working.diffs.append(
        "--- a/obsolete.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-print('old')\n"
    )

    assert coordinator.list_changes()[0]["path"] == "obsolete.py"


def test_diff_content_starting_with_two_pluses_is_counted_as_content(tmp_path: Path) -> None:
    coordinator = TurnCoordinator()
    runtime = FakeRuntime(coordinator.handle_agent_event)
    coordinator.attach_runtime(runtime)
    coordinator.configure_workspace_services(
        workspace=tmp_path,
        sessions=SessionStore(tmp_path / "data"),
    )
    coordinator.new_session()
    runtime.controllers[-1].working.diffs.append(
        "--- a/demo.md\n+++ b/demo.md\n@@ -0,0 +1 @@\n+++ heading\n"
    )

    change = coordinator.list_changes()[0]
    assert change["path"] == "demo.md"
    assert change["additions"] == 1


def test_repeated_edits_to_one_path_keep_independent_unified_diffs(tmp_path: Path) -> None:
    coordinator = TurnCoordinator()
    runtime = FakeRuntime(coordinator.handle_agent_event)
    coordinator.attach_runtime(runtime)
    coordinator.configure_workspace_services(
        workspace=tmp_path,
        sessions=SessionStore(tmp_path / "data"),
    )
    coordinator.new_session()
    runtime.controllers[-1].working.diffs.extend(
        [
            "--- a/demo.py\n+++ b/demo.py\n@@ -0,0 +1 @@\n+first\n",
            "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1,2 @@\n first\n+second\n",
        ]
    )

    changes = coordinator.list_changes()
    assert len(changes) == 2
    assert [change["path"] for change in changes] == ["demo.py", "demo.py"]
    assert [change["additions"] for change in changes] == [1, 1]
    assert changes[1]["diff"].startswith("--- a/demo.py\n+++ b/demo.py")


def test_coordinator_exposes_only_recorded_changes_and_safe_preview(tmp_path: Path) -> None:
    source = tmp_path / "demo.py"
    source.write_text("answer = 42", encoding="utf-8")
    coordinator = TurnCoordinator()
    runtime = FakeRuntime(coordinator.handle_agent_event)
    coordinator.attach_runtime(runtime)
    coordinator.configure_workspace_services(
        workspace=tmp_path,
        sessions=SessionStore(tmp_path / "data"),
    )
    coordinator.new_session()
    runtime.controllers[-1].working.diffs.append(
        "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-answer = 41\n+answer = 42\n"
    )

    assert coordinator.preview_file("demo.py")["text"] == "answer = 42"
    assert coordinator.list_changes() == [
        {
            "id": "change-1",
            "path": "demo.py",
            "additions": 1,
            "deletions": 1,
            "diff": "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-answer = 41\n+answer = 42\n",
        }
    ]
