from __future__ import annotations

import re
from typing import Protocol, cast

SERVICE_NAME = "forge-coding-agent"
_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*:[a-z0-9][a-z0-9._-]*$")


class CredentialStoreError(RuntimeError):
    pass


class CredentialService(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def persistent(self) -> bool: ...

    def get(self, reference: str) -> str | None: ...

    def set(self, reference: str, secret: str) -> None: ...

    def delete(self, reference: str) -> None: ...


class KeyringBackend(Protocol):
    priority: float

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def provider_credential_ref(provider: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", provider.casefold()).strip("-")
    if not normalized:
        raise CredentialStoreError("provider name must contain a letter or number")
    return f"provider:{normalized}"


def _validate_reference(reference: str) -> None:
    if not _REFERENCE.fullmatch(reference):
        raise CredentialStoreError("invalid credential reference")


class KeyringCredentialService:
    def __init__(self, *, backend: KeyringBackend | None = None) -> None:
        if backend is None:
            import keyring

            resolved_backend = cast(KeyringBackend, keyring.get_keyring())
        else:
            resolved_backend = backend
        self._backend = resolved_backend

    @property
    def available(self) -> bool:
        identity = f"{type(self._backend).__module__}.{type(self._backend).__name__}".casefold()
        insecure = ("plaintext", "keyrings.alt", "backends.fail", "backends.null")
        try:
            priority = float(self._backend.priority)
        except (TypeError, ValueError):
            return False
        return priority > 0 and not any(marker in identity for marker in insecure)

    @property
    def persistent(self) -> bool:
        return self.available

    def get(self, reference: str) -> str | None:
        self._ensure_available(reference)
        try:
            return self._backend.get_password(SERVICE_NAME, reference)
        except Exception as exc:
            raise CredentialStoreError("cannot read secure credential storage") from exc

    def set(self, reference: str, secret: str) -> None:
        self._ensure_available(reference)
        if not secret:
            raise CredentialStoreError("credential must not be empty")
        try:
            self._backend.set_password(SERVICE_NAME, reference, secret)
        except Exception as exc:
            raise CredentialStoreError("cannot write secure credential storage") from exc

    def delete(self, reference: str) -> None:
        self._ensure_available(reference)
        try:
            self._backend.delete_password(SERVICE_NAME, reference)
        except Exception as exc:
            if "not found" not in str(exc).casefold():
                raise CredentialStoreError("cannot delete secure credential") from exc

    def _ensure_available(self, reference: str) -> None:
        _validate_reference(reference)
        if not self.available:
            raise CredentialStoreError("secure credential storage is unavailable")

    def __repr__(self) -> str:
        return f"KeyringCredentialService(available={self.available})"


class MemoryCredentialService:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return True

    @property
    def persistent(self) -> bool:
        return False

    def get(self, reference: str) -> str | None:
        _validate_reference(reference)
        return self._values.get(reference)

    def set(self, reference: str, secret: str) -> None:
        _validate_reference(reference)
        if not secret:
            raise CredentialStoreError("credential must not be empty")
        self._values[reference] = secret

    def delete(self, reference: str) -> None:
        _validate_reference(reference)
        self._values.pop(reference, None)

    def __repr__(self) -> str:
        return f"MemoryCredentialService(entries={len(self._values)})"
