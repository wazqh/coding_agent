from __future__ import annotations

import json

import pytest

from coding_agent.web.handshake import (
    DESKTOP_HANDSHAKE_PREFIX,
    DesktopHandshake,
    serialize_desktop_handshake,
)


def test_desktop_handshake_is_one_ascii_json_line() -> None:
    line = serialize_desktop_handshake(
        DesktopHandshake(
            origin="http://127.0.0.1:43210",
            capability="launch-secret",
        )
    )

    assert line.startswith(DESKTOP_HANDSHAKE_PREFIX)
    assert "\n" not in line and "\r" not in line
    payload = json.loads(line.removeprefix(DESKTOP_HANDSHAKE_PREFIX))
    assert payload == {
        "origin": "http://127.0.0.1:43210",
        "capability": "launch-secret",
    }
    line.encode("ascii")


@pytest.mark.parametrize(
    ("origin", "capability"),
    [
        ("https://example.com", "valid-capability"),
        ("http://127.0.0.1:43210/path", "valid-capability"),
        ("http://127.0.0.1:43210", "line\nbreak"),
        ("http://127.0.0.1:43210", ""),
    ],
)
def test_desktop_handshake_rejects_unsafe_values(origin: str, capability: str) -> None:
    with pytest.raises(ValueError):
        serialize_desktop_handshake(DesktopHandshake(origin=origin, capability=capability))
