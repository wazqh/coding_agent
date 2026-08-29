from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from coding_agent.safety.paths import atomic_write_text


class ModelCatalogError(ValueError):
    pass


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str | None = None
    api_key_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    default_model: str = Field(min_length=1)
    models: list[str] = Field(default_factory=list)
    compatibility: Literal["openai", "gemini"] = "openai"


class CatalogConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_provider: str | None = None
    providers: dict[str, ProviderProfile] = Field(default_factory=dict)


class ModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    model: str
    base_url: str | None = None
    api_key: str = Field(repr=False)
    compatibility: Literal["openai", "gemini"] = "openai"


class ActiveModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    model: str


class ModelCatalog:
    def __init__(self, *, path: Path, environ: Mapping[str, str]) -> None:
        self.path = path
        self.environ = environ
        self.config = CatalogConfig()
        self.reload()

    @property
    def default_provider(self) -> str | None:
        return self.config.default_provider

    def providers(self) -> list[str]:
        return list(self.config.providers)

    def reload(self) -> None:
        if not self.path.is_file():
            self.config = CatalogConfig()
            return
        try:
            with self.path.open("rb") as stream:
                value = tomllib.load(stream)
            config = CatalogConfig.model_validate(value)
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise ModelCatalogError(f"cannot read model catalog {self.path}: {exc}") from exc
        if config.providers and config.default_provider not in config.providers:
            raise ModelCatalogError("default_provider must name a configured provider")
        self.config = config

    def resolve(self, provider: str, model: str | None = None) -> ModelSelection:
        profile = self.config.providers.get(provider)
        if profile is None:
            raise ModelCatalogError(f"unknown provider: {provider}")
        model_name = model or profile.default_model
        if profile.models and model_name not in profile.models:
            raise ModelCatalogError(f"model {model_name!r} is not configured for {provider}")
        api_key = self.environ.get(profile.api_key_env)
        if not api_key:
            raise ModelCatalogError(f"environment variable {profile.api_key_env} is not set")
        return ModelSelection(
            provider=provider,
            model=model_name,
            base_url=profile.base_url,
            api_key=api_key,
            compatibility=profile.compatibility,
        )


class ModelSelectionStore:
    def __init__(self, *, data_dir: Path) -> None:
        self.path = data_dir / "model-selection.json"

    def load(self) -> ActiveModelSelection | None:
        if not self.path.is_file():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return ActiveModelSelection.model_validate(value)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ModelCatalogError(f"cannot read active model selection: {exc}") from exc

    def save(self, *, provider: str, model: str) -> None:
        selection = ActiveModelSelection(provider=provider, model=model)
        payload = selection.model_dump(mode="json")
        atomic_write_text(self.path, json.dumps(payload, indent=2) + "\n")
