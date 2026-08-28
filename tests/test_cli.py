from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("typer")
from typer.testing import CliRunner

from coding_agent.cli import app


def test_version_and_help() -> None:
    runner = CliRunner()
    version = runner.invoke(app, ["--version"])
    help_result = runner.invoke(app, ["--help"])
    assert version.exit_code == 0 and "0.1.0" in version.stdout
    assert help_result.exit_code == 0
    assert "sessions" in help_result.stdout and "resume" in help_result.stdout


def test_sessions_json_uses_configured_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODING_AGENT_DATA_DIR", str(tmp_path / "data"))
    result = CliRunner().invoke(app, ["sessions", "--output", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_noninteractive_missing_key_is_configuration_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODING_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = CliRunner().invoke(
        app,
        ["run", "inspect", "--cwd", str(tmp_path), "--output", "jsonl"],
    )
    assert result.exit_code == 2
    assert "OPENAI_API_KEY" in result.stderr


def test_sessions_rejects_unknown_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODING_AGENT_DATA_DIR", str(tmp_path / "data"))
    result = CliRunner().invoke(app, ["sessions", "--output", "yaml"])
    assert result.exit_code == 2
