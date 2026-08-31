from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from coding_agent.credentials import (
    CredentialService,
    CredentialStoreError,
    KeyringCredentialService,
)


def execute(
    action: str,
    reference: str,
    value: str,
    service: CredentialService,
) -> dict[str, object]:
    if action == "has":
        return {
            "ok": True,
            "present": service.get(reference) is not None,
            "persistent": service.persistent,
        }
    if action == "set":
        if not value:
            raise CredentialStoreError("credential must not be empty")
        if "\n" in value or "\r" in value:
            raise CredentialStoreError("credential must not contain line breaks")
        service.set(reference, value)
        return {"ok": True, "persisted": service.persistent}
    if action == "copy":
        if not value:
            raise CredentialStoreError("destination credential is required")
        if value == reference:
            raise CredentialStoreError("source and destination credentials must differ")
        source = service.get(reference)
        if source is None:
            raise CredentialStoreError("source credential was not found")
        if service.get(value) is not None:
            raise CredentialStoreError("destination credential already exists")
        service.set(value, source)
        return {"ok": True, "persisted": service.persistent}
    if action == "delete":
        service.delete(reference)
        return {"ok": True}
    raise CredentialStoreError("unsupported credential action")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("action", choices=("has", "set", "copy", "delete"))
    parser.add_argument("reference")
    parser.add_argument("target", nargs="?")
    values = parser.parse_args(argv)
    value = sys.stdin.read(16_385) if values.action == "set" else (values.target or "")
    try:
        if len(value) > 16_384:
            raise CredentialStoreError("credential is too long")
        result = execute(
            values.action,
            values.reference,
            value,
            KeyringCredentialService(),
        )
    except CredentialStoreError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
