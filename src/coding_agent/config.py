from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError


class ConfigError(ValueError):
    pass


class AgentSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_steps: int = Field(default=24, ge=12, le=100)
    max_seconds: int = Field(default=600, ge=10, le=3600)
    context_window: int = Field(default=32768, ge=4096)
    command_timeout: int = Field(default=120, ge=1, le=300)
    _configured_max_steps: int = PrivateAttr(default=24)

    @property
    def configured_max_steps(self) -> int:
        return self._configured_max_steps

    def capture_configured_max_steps(self) -> None:
        self._configured_max_steps = self.max_steps


class MemorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    max_injected_tokens: int = Field(default=2000, ge=0, le=8000)


class SkillSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    implicit_activation: bool = True


class UISettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: str = "forge-dark"
    raw_tool_output: bool = False


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "deepseek-chat"
    base_url: str | None = None
    api_key: str | None = Field(default=None, repr=False)
    max_retries: int = Field(default=3, ge=0, le=6)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cwd: Path
    data_dir: Path
    agent: AgentSettings = Field(default_factory=AgentSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    skills: SkillSettings = Field(default_factory=SkillSettings)
    ui: UISettings = Field(default_factory=UISettings)
    model: ModelSettings = Field(default_factory=ModelSettings)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _project_config(cwd: Path, *, trusted: bool) -> dict[str, Any]:
    path = cwd / "coding-agent.toml"
    if not trusted or not path.is_file():
        return {}
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must contain a TOML table")
    model_values = value.get("model")
    if isinstance(model_values, dict) and "api_key" in model_values:
        raise ConfigError("API keys are only accepted through OPENAI_API_KEY")
    return value


def load_settings(
    cwd: Path | str,
    *,
    trusted_project: bool = False,
    cli: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
    data_dir: Path | None = None,
) -> Settings:
    """Load defaults < trusted project TOML < environment < CLI."""

    root = Path(cwd).expanduser().resolve()
    if not root.is_dir():
        raise ConfigError(f"workspace is not a directory: {root}")
    env = os.environ if environ is None else environ
    values: dict[str, Any] = _project_config(root, trusted=trusted_project)
    env_values: dict[str, Any] = {"model": {}}
    if env.get("OPENAI_API_KEY"):
        env_values["model"]["api_key"] = env["OPENAI_API_KEY"]
    if env.get("OPENAI_BASE_URL"):
        env_values["model"]["base_url"] = env["OPENAI_BASE_URL"]
    if env.get("CODING_AGENT_MODEL"):
        env_values["model"]["name"] = env["CODING_AGENT_MODEL"]
    values = _deep_merge(values, env_values)
    if cli:
        values = _deep_merge(values, cli)
    values["cwd"] = root
    values["data_dir"] = data_dir or user_data_path("coding-agent", "forge", ensure_exists=True)
    try:
        return Settings.model_validate(values)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc
