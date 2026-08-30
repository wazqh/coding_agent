from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import pytest

pytest.importorskip("typer")
from typer.testing import CliRunner

import coding_agent.cli as cli_module
from coding_agent.cli import _build_runtime, app
from coding_agent.workspace_settings import WorkspaceSettingsStore


def test_version_and_help() -> None:
    runner = CliRunner()
    version = runner.invoke(app, ["--version"])
    help_result = runner.invoke(app, ["--help"])
    assert version.exit_code == 0 and "1.0.0" in version.stdout
    assert help_result.exit_code == 0
    assert "sessions" in help_result.stdout and "resume" in help_result.stdout


def test_web_command_reports_exact_optional_install_when_dependency_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_launcher() -> NoReturn:
        error = ModuleNotFoundError("No module named 'fastapi'")
        error.name = "fastapi"
        raise error

    monkeypatch.setattr(cli_module, "_load_web_launcher", missing_launcher, raising=False)

    result = CliRunner().invoke(app, ["web", "--cwd", str(tmp_path)])

    assert result.exit_code == 2
    assert 'pip install -e ".[web]"' in result.stderr


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


def test_runtime_restores_workspace_max_steps_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CODING_AGENT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    WorkspaceSettingsStore(data_dir=data_dir, workspace=tmp_path).set_max_steps(48)

    controller, _, _ = _build_runtime(
        cwd=tmp_path,
        model_name=None,
        permissions="read-only",
        interactive=False,
        output="jsonl",
        trust_project=False,
    )

    assert controller.settings.agent.max_steps == 48


def test_runtime_uses_persisted_provider_without_openai_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "models.toml").write_text(
        """
default_provider = "gemini"
[providers.gemini]
base_url = "https://gemini.example/v1"
api_key_env = "GEMINI_API_KEY"
default_model = "gemini-flash"
models = ["gemini-flash", "gemini-pro"]
compatibility = "gemini"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODING_AGENT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    controller, _, _ = _build_runtime(
        cwd=tmp_path,
        model_name="gemini-pro",
        permissions="read-only",
        interactive=False,
        output="jsonl",
        trust_project=False,
    )

    assert controller.settings.model.name == "gemini-pro"
    assert controller.settings.model.base_url == "https://gemini.example/v1"
    assert controller.model.compatibility == "gemini"
    assert controller.model_manager is not None
    assert controller.model_manager.provider == "gemini"
