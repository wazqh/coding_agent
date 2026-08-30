from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

DESKTOP_HANDSHAKE_PREFIX = "FORGE_DESKTOP_READY "
_CAPABILITY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,512}$")


@dataclass(frozen=True)
class DesktopHandshake:
    origin: str
    capability: str


def serialize_desktop_handshake(value: DesktopHandshake) -> str:
    parsed = urlsplit(value.origin)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("desktop origin has an invalid port") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("desktop origin must be an unadorned loopback HTTP origin")
    if not _CAPABILITY_PATTERN.fullmatch(value.capability):
        raise ValueError("desktop capability is invalid")
    payload = json.dumps(asdict(value), ensure_ascii=True, separators=(",", ":"))
    return f"{DESKTOP_HANDSHAKE_PREFIX}{payload}"
