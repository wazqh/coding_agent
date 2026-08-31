from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from coding_agent.credentials import CredentialService, provider_credential_ref
from coding_agent.safety.paths import atomic_write_text


class ModelCatalogError(ValueError):
    pass


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str | None = None
    api_key_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    credential_ref: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9._-]*:[a-z0-9][a-z0-9._-]*$"
    )
    default_model: str = Field(min_length=1)
    models: list[str] = Field(default_factory=list)
    compatibility: Literal["openai", "gemini"] = "openai"

    @model_validator(mode="after")
    def include_default_in_explicit_model_list(self) -> ProviderProfile:
        if self.models and self.default_model not in self.models:
            self.models.insert(0, self.default_model)
        return self


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
    def __init__(
        self,
        *,
        path: Path,
        environ: Mapping[str, str],
        credentials: CredentialService | None = None,
    ) -> None:
        self.path = path
        self.environ = environ
        self.credentials = credentials
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
        credential_ref = profile.credential_ref or provider_credential_ref(provider)
        if not api_key and self.credentials is not None and self.credentials.available:
            api_key = self.credentials.get(credential_ref)
        if not api_key:
            raise ModelCatalogError(
                f"credential for {provider!r} is not configured; set {profile.api_key_env} "
                "or save it with Forge model settings"
            )
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
