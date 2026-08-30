from __future__ import annotations

from typing import ClassVar

import pytest

from coding_agent.credentials import (
    CredentialStoreError,
    KeyringCredentialService,
    MemoryCredentialService,
    provider_credential_ref,
)


class FakeKeyring:
    priority = 5
    values: ClassVar[dict[tuple[str, str], str]] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_provider_credential_ref_is_stable_and_rejects_empty_names() -> None:
    assert provider_credential_ref("Google Gemini") == "provider:google-gemini"
    with pytest.raises(CredentialStoreError, match="letter or number"):
        provider_credential_ref("---")


def test_keyring_service_round_trips_without_exposing_secret_in_repr() -> None:
    FakeKeyring.values = {}
    service = KeyringCredentialService(backend=FakeKeyring())

    service.set("provider:gemini", "top-secret")

    assert service.get("provider:gemini") == "top-secret"
    assert "top-secret" not in repr(service)
    service.delete("provider:gemini")
    assert service.get("provider:gemini") is None


def test_memory_service_reports_that_credentials_are_not_persistent() -> None:
    service = MemoryCredentialService()
    service.set("provider:gemini", "temporary-secret")

    assert service.get("provider:gemini") == "temporary-secret"
    assert service.persistent is False
    assert "temporary-secret" not in repr(service)


def test_keyring_service_rejects_plaintext_or_failed_backends() -> None:
    class PlaintextKeyring(FakeKeyring):
        priority = 1

    PlaintextKeyring.__module__ = "keyrings.alt.file"

    service = KeyringCredentialService(backend=PlaintextKeyring())

    assert service.available is False
    with pytest.raises(CredentialStoreError, match="secure credential storage"):
        service.set("provider:gemini", "secret")
