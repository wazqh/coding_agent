from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import ValidationError

from coding_agent.credentials import provider_credential_ref
from coding_agent.model_catalog import CatalogConfig, ModelCatalogError, ProviderProfile
from coding_agent.safety.paths import atomic_write_text

_PROVIDER_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class ProviderProfileResult:
    provider: str
    model: str
    api_key_env: str
    credential_ref: str


def provider_api_key_env(provider: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", provider).strip("_").upper()
    if not normalized:
        raise ValueError("provider must contain a letter or number")
    return f"FORGE_PROVIDER_{normalized}_API_KEY"


class ModelProfileWriter:
    """Atomically updates provider metadata without ever accepting credentials."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def upsert(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        compatibility: Literal["openai", "gemini"] = "openai",
    ) -> ProviderProfileResult:
        provider = provider.strip()
        base_url = base_url.strip().rstrip("/")
        model = model.strip()
        if not _PROVIDER_PATTERN.fullmatch(provider):
            raise ValueError("provider must use only letters, numbers, '.', '_' or '-'")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Base URL must be an HTTP or HTTPS URL")
        if not model:
            raise ValueError("model must not be empty")

        config = self._load()
        api_key_env = provider_api_key_env(provider)
        credential_ref = provider_credential_ref(provider)
        existing = config.providers.get(provider)
        existing_models = [] if existing is None else list(existing.models)
        models = list(dict.fromkeys([model, *existing_models]))
        config.providers[provider] = ProviderProfile(
            base_url=base_url,
            api_key_env=api_key_env,
            credential_ref=credential_ref,
            default_model=model,
            models=models,
            compatibility=compatibility,
        )
        if config.default_provider is None:
            config.default_provider = provider
        atomic_write_text(self.path, _render_catalog(config))
        return ProviderProfileResult(
            provider=provider,
            model=model,
            api_key_env=api_key_env,
            credential_ref=credential_ref,
        )

    def _load(self) -> CatalogConfig:
        if not self.path.is_file():
            return CatalogConfig()
        try:
            with self.path.open("rb") as stream:
                return CatalogConfig.model_validate(tomllib.load(stream))
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise ModelCatalogError(f"cannot update model catalog {self.path}: {exc}") from exc


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_catalog(config: CatalogConfig) -> str:
    lines: list[str] = []
    if config.default_provider is not None:
        lines.append(f"default_provider = {_toml_string(config.default_provider)}")
    for name, profile in config.providers.items():
        if lines:
            lines.append("")
        lines.append(f"[providers.{_toml_string(name)}]")
        if profile.base_url is not None:
            lines.append(f"base_url = {_toml_string(profile.base_url)}")
        lines.append(f"api_key_env = {_toml_string(profile.api_key_env)}")
        if profile.credential_ref is not None:
            lines.append(f"credential_ref = {_toml_string(profile.credential_ref)}")
        lines.append(f"default_model = {_toml_string(profile.default_model)}")
        models = ", ".join(_toml_string(item) for item in profile.models)
        lines.append(f"models = [{models}]")
        lines.append(f"compatibility = {_toml_string(profile.compatibility)}")
    return "\n".join(lines) + "\n"
