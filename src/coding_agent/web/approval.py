from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, Lock
from uuid import uuid4

from coding_agent.safety.approval import ApprovalDecision, ApprovalRequest

ApprovalPublisher = Callable[[str, ApprovalRequest], None]


@dataclass
class _PendingApproval:
    ready: Event = field(default_factory=Event)
    decision: ApprovalDecision = ApprovalDecision.DENY


class ApprovalBroker:
    """Bridge a synchronous approval callback to an asynchronous graphical client."""

    def __init__(self, *, on_request: ApprovalPublisher) -> None:
        self._on_request = on_request
        self._lock = Lock()
        self._pending: dict[str, _PendingApproval] = {}
        self._closed = False

    @property
    def pending_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._pending)

    def request(self, request: ApprovalRequest) -> ApprovalDecision:
        approval_id = uuid4().hex
        pending = _PendingApproval()
        with self._lock:
            if self._closed:
                return ApprovalDecision.DENY
            self._pending[approval_id] = pending
        try:
            self._on_request(approval_id, request)
        except Exception:
            with self._lock:
                self._pending.pop(approval_id, None)
            return ApprovalDecision.DENY

        pending.ready.wait()
        with self._lock:
            self._pending.pop(approval_id, None)
        return pending.decision

    def resolve(self, approval_id: str, decision: ApprovalDecision) -> bool:
        with self._lock:
            pending = self._pending.pop(approval_id, None)
            if pending is None or pending.ready.is_set():
                return False
            pending.decision = decision
            pending.ready.set()
            return True

    def cancel_all(self) -> int:
        return len(self.cancel_pending())

    def cancel_pending(self) -> tuple[str, ...]:
        """Deny every waiter and return the exact opaque IDs that were cancelled."""

        with self._lock:
            pending = tuple(self._pending.items())
            self._pending.clear()
            for _, item in pending:
                item.decision = ApprovalDecision.DENY
                item.ready.set()
            return tuple(approval_id for approval_id, _ in pending)

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self.cancel_all()
