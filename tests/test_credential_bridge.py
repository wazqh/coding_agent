from __future__ import annotations

import json

import pytest

from coding_agent.credential_bridge import execute
from coding_agent.credentials import CredentialStoreError, MemoryCredentialService


def test_bridge_sets_checks_and_deletes_without_returning_the_secret() -> None:
    service = MemoryCredentialService()

    saved = execute("set", "provider:gemini", "top-secret", service)
    checked = execute("has", "provider:gemini", "", service)
    deleted = execute("delete", "provider:gemini", "", service)

    output = json.dumps([saved, checked, deleted])
    assert saved == {"ok": True, "persisted": False}
    assert checked == {"ok": True, "present": True, "persistent": False}
    assert deleted == {"ok": True}
    assert "top-secret" not in output


def test_bridge_rejects_empty_or_multiline_secrets() -> None:
    service = MemoryCredentialService()

    with pytest.raises(CredentialStoreError, match="empty"):
        execute("set", "provider:gemini", "", service)
    with pytest.raises(CredentialStoreError, match="line breaks"):
        execute("set", "provider:gemini", "first\nsecond", service)


def test_bridge_copies_a_secret_without_returning_it() -> None:
    service = MemoryCredentialService()
    service.set("provider:source", "top-secret")

    copied = execute("copy", "provider:source", "provider:target", service)

    assert copied == {"ok": True, "persisted": False}
    assert service.get("provider:target") == "top-secret"
    assert "top-secret" not in json.dumps(copied)


def test_bridge_copy_requires_a_source_and_empty_destination() -> None:
    service = MemoryCredentialService()

    with pytest.raises(CredentialStoreError, match="source credential"):
        execute("copy", "provider:missing", "provider:target", service)

    service.set("provider:source", "source-secret")
    service.set("provider:target", "target-secret")
    with pytest.raises(CredentialStoreError, match="destination credential"):
        execute("copy", "provider:source", "provider:target", service)
