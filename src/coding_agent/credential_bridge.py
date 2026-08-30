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
    secret: str,
    service: CredentialService,
) -> dict[str, object]:
    if action == "has":
        return {
            "ok": True,
            "present": service.get(reference) is not None,
            "persistent": service.persistent,
        }
    if action == "set":
        if not secret:
            raise CredentialStoreError("credential must not be empty")
        if "\n" in secret or "\r" in secret:
            raise CredentialStoreError("credential must not contain line breaks")
        service.set(reference, secret)
        return {"ok": True, "persisted": service.persistent}
    if action == "delete":
        service.delete(reference)
        return {"ok": True}
    raise CredentialStoreError("unsupported credential action")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("action", choices=("has", "set", "delete"))
    parser.add_argument("reference")
    values = parser.parse_args(argv)
    secret = sys.stdin.read(16_385) if values.action == "set" else ""
    try:
        if len(secret) > 16_384:
            raise CredentialStoreError("credential is too long")
        result = execute(
            values.action,
            values.reference,
            secret,
            KeyringCredentialService(),
        )
    except CredentialStoreError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
