from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.config import ConfigError, load_settings


def test_config_priority_and_untrusted_project(tmp_path: Path) -> None:
    (tmp_path / "coding-agent.toml").write_text(
        "[agent]\nmax_steps=30\n[model]\nname='project'\nrequest_timeout=45\n",
        encoding="utf-8",
    )
    untrusted = load_settings(
        tmp_path,
        trusted_project=False,
        environ={"CODING_AGENT_MODEL": "env", "OPENAI_API_KEY": "secret"},
        data_dir=tmp_path / "data",
    )
    assert untrusted.agent.max_steps == 40
    assert untrusted.model.name == "env"
    trusted = load_settings(
        tmp_path,
        trusted_project=True,
        environ={"CODING_AGENT_MODEL": "env", "OPENAI_API_KEY": "secret"},
        cli={"model": {"name": "cli"}, "agent": {"max_steps": 31}},
        data_dir=tmp_path / "data",
    )
    assert trusted.agent.max_steps == 31
    assert trusted.model.name == "cli"
    assert trusted.model.request_timeout == 45


def test_invalid_config_and_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ConfigError):
        load_settings(missing, data_dir=tmp_path / "data")
    (tmp_path / "coding-agent.toml").write_text("[agent]\nmax_steps=0", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(tmp_path, trusted_project=True, data_dir=tmp_path / "data")


def test_max_steps_rejects_values_outside_supported_range(tmp_path: Path) -> None:
    (tmp_path / "coding-agent.toml").write_text("[agent]\nmax_steps=29\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_settings(tmp_path, trusted_project=True, data_dir=tmp_path / "data")

    (tmp_path / "coding-agent.toml").write_text("[agent]\nmax_steps=1000\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_settings(tmp_path, trusted_project=True, data_dir=tmp_path / "data")
