from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.config import ConfigError, load_settings


def test_config_priority_and_untrusted_project(tmp_path: Path) -> None:
    (tmp_path / "coding-agent.toml").write_text(
        "[agent]\nmax_steps=7\n[model]\nname='project'\n", encoding="utf-8"
    )
    untrusted = load_settings(
        tmp_path,
        trusted_project=False,
        environ={"CODING_AGENT_MODEL": "env", "OPENAI_API_KEY": "secret"},
        data_dir=tmp_path / "data",
    )
    assert untrusted.agent.max_steps == 24
    assert untrusted.model.name == "env"
    trusted = load_settings(
        tmp_path,
        trusted_project=True,
        environ={"CODING_AGENT_MODEL": "env", "OPENAI_API_KEY": "secret"},
        cli={"model": {"name": "cli"}, "agent": {"max_steps": 3}},
        data_dir=tmp_path / "data",
    )
    assert trusted.agent.max_steps == 3
    assert trusted.model.name == "cli"


def test_invalid_config_and_workspace(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ConfigError):
        load_settings(missing, data_dir=tmp_path / "data")
    (tmp_path / "coding-agent.toml").write_text("[agent]\nmax_steps=0", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(tmp_path, trusted_project=True, data_dir=tmp_path / "data")
