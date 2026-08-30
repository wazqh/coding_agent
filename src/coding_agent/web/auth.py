from __future__ import annotations

import hmac
import secrets
from threading import Lock


class LaunchAuth:
    """Single-launch capability exchange and one-controller authorization."""

    cookie_name = "forge_session"

    def __init__(self, *, host: str, origin: str) -> None:
        self.host = host
        self.origin = origin
        self.capability = secrets.token_urlsafe(32)
        self._session_token = secrets.token_urlsafe(32)
        self._capability_used = False
        self._revoked = False
        self._controller_claimed = False
        self._lock = Lock()

    def _location_matches(self, *, host: str, origin: str) -> bool:
        return hmac.compare_digest(host, self.host) and hmac.compare_digest(origin, self.origin)

    def exchange(self, capability: str, *, host: str, origin: str) -> str | None:
        with self._lock:
            if self._revoked or self._capability_used:
                return None
            if not self._location_matches(host=host, origin=origin):
                return None
            if not hmac.compare_digest(capability, self.capability):
                return None
            self._capability_used = True
            return self._session_token

    def authorize(self, token: str | None, *, host: str, origin: str) -> bool:
        if token is None:
            return False
        with self._lock:
            return (
                not self._revoked
                and self._location_matches(host=host, origin=origin)
                and hmac.compare_digest(token, self._session_token)
            )

    def claim_controller(self, token: str) -> bool:
        with self._lock:
            if self._revoked or self._controller_claimed:
                return False
            if not hmac.compare_digest(token, self._session_token):
                return False
            self._controller_claimed = True
            return True

    def release_controller(self, token: str) -> None:
        with self._lock:
            if hmac.compare_digest(token, self._session_token):
                self._controller_claimed = False

    def revoke(self) -> None:
        with self._lock:
            self._revoked = True
            self._controller_claimed = False
