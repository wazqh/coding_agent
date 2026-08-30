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
