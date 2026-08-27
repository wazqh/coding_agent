from __future__ import annotations

import hashlib
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel


class ApprovalDecision(StrEnum):
    ALLOW_ONCE = "allow_once"
    ALLOW_SESSION = "allow_session"
    DENY = "deny"


class ApprovalRequest(BaseModel):
    action: str
    subject: str
    summary: str
    diff: str | None = None

    @property
    def fingerprint(self) -> str:
        raw = f"{self.action}\0{self.subject}".encode()
        return hashlib.sha256(raw).hexdigest()


ApprovalCallback = Callable[[ApprovalRequest], ApprovalDecision]


class ApprovalPolicy:
    """Central approval gate shared by every mutating tool."""

    def __init__(
        self,
        mode: str = "prompt",
        *,
        interactive: bool = True,
        callback: ApprovalCallback | None = None,
    ) -> None:
        if mode not in {"prompt", "auto", "read-only"}:
            raise ValueError(f"unknown permission mode: {mode}")
        self.mode = mode
        self.interactive = interactive
        self.callback = callback
        self._session_grants: set[str] = set()
        self.denied = False

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        if self.mode == "read-only":
            self.denied = True
            return ApprovalDecision.DENY
        if self.mode == "auto" or request.fingerprint in self._session_grants:
            return ApprovalDecision.ALLOW_ONCE
        if not self.interactive or self.callback is None:
            self.denied = True
            return ApprovalDecision.DENY
        decision = self.callback(request)
        if decision is ApprovalDecision.ALLOW_SESSION:
            self._session_grants.add(request.fingerprint)
        elif decision is ApprovalDecision.DENY:
            self.denied = True
        return decision

