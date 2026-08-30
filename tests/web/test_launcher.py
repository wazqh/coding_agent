from __future__ import annotations

from pathlib import Path

import pytest

import coding_agent.web.launcher as launcher_module
from coding_agent.config import ConfigError
from coding_agent.web.handshake import DESKTOP_HANDSHAKE_PREFIX
from coding_agent.web.launcher import _loopback_listener, launch_web


def test_listener_uses_loopback_and_os_assigned_port() -> None:
    listener = _loopback_listener()
    try:
        host, port = listener.getsockname()
        assert host == "127.0.0.1"
        assert isinstance(port, int) and port > 0
    finally:
        listener.close()


def test_launcher_rejects_missing_built_assets_before_runtime_start(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Web UI assets are not built"):
        launch_web(
            workspace=tmp_path,
            data_dir=tmp_path / "data",
            model_name=None,
            permissions="prompt",
            trusted_project=False,
            open_browser=False,
            static_dir=tmp_path / "missing",
        )


def test_launcher_uses_private_desktop_handshake_instead_of_human_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assets = tmp_path / "static"
    assets.mkdir()
    (assets / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(launcher_module.uvicorn.Server, "run", lambda *args, **kwargs: None)
    handshakes: list[str] = []

    result = launch_web(
        workspace=tmp_path,
        data_dir=tmp_path / "data",
        model_name=None,
        permissions="prompt",
        trusted_project=False,
        open_browser=False,
        static_dir=assets,
        desktop_handshake=handshakes.append,
    )

    assert result == 0
    assert len(handshakes) == 1
    assert handshakes[0].startswith(DESKTOP_HANDSHAKE_PREFIX)
    assert capsys.readouterr().out == ""
