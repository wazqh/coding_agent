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
_RESOURCE_ENDPOINT_PATTERN = re.compile(
    r"/(?:chat/completions|completions|responses|models)$",
    re.IGNORECASE,
)


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
        base_url = _normalize_base_url(base_url)
        model = model.strip()
        if not _PROVIDER_PATTERN.fullmatch(provider):
            raise ValueError("provider must use only letters, numbers, '.', '_' or '-'")
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

    def delete(self, provider: str) -> None:
        provider = provider.strip()
        config = self._load()
        if provider not in config.providers:
            raise ValueError(f"unknown provider: {provider}")
        if len(config.providers) == 1:
            raise ValueError("cannot delete the last provider")
        del config.providers[provider]
        if config.default_provider == provider:
            config.default_provider = next(iter(config.providers))
        atomic_write_text(self.path, _render_catalog(config))

    def update_model(
        self,
        *,
        provider: str,
        original_model: str,
        model: str,
        base_url: str,
        compatibility: Literal["openai", "gemini"] = "openai",
    ) -> ProviderProfileResult:
        provider = provider.strip()
        original_model = original_model.strip()
        model = model.strip()
        base_url = _normalize_base_url(base_url)
        if not _PROVIDER_PATTERN.fullmatch(provider):
            raise ValueError("provider must use only letters, numbers, '.', '_' or '-'")
        if not original_model or not model:
            raise ValueError("model names must not be empty")

        config = self._load()
        existing = config.providers.get(provider)
        if existing is None:
            raise ValueError(f"unknown provider: {provider}")
        models = list(existing.models or [existing.default_model])
        if original_model not in models:
            raise ValueError(f"unknown model for {provider}: {original_model}")
        if model != original_model and model in models:
            raise ValueError(f"model already exists for {provider}: {model}")
        models[models.index(original_model)] = model
        default_model = (
            model if existing.default_model == original_model else existing.default_model
        )
        config.providers[provider] = ProviderProfile(
            base_url=base_url,
            api_key_env=existing.api_key_env,
            credential_ref=existing.credential_ref,
            default_model=default_model,
            models=models,
            compatibility=compatibility,
        )
        atomic_write_text(self.path, _render_catalog(config))
        return ProviderProfileResult(
            provider=provider,
            model=model,
            api_key_env=existing.api_key_env,
            credential_ref=existing.credential_ref or provider_credential_ref(provider),
        )

    def delete_model(self, provider: str, model: str) -> bool:
        """Delete one model and return whether its provider was removed too."""

        provider = provider.strip()
        model = model.strip()
        config = self._load()
        existing = config.providers.get(provider)
        if existing is None:
            raise ValueError(f"unknown provider: {provider}")
        models = list(existing.models or [existing.default_model])
        if model not in models:
            raise ValueError(f"unknown model for {provider}: {model}")
        models.remove(model)
        if not models:
            del config.providers[provider]
            if config.default_provider == provider:
                config.default_provider = next(iter(config.providers), None)
            atomic_write_text(self.path, _render_catalog(config))
            return True

        default_model = existing.default_model if existing.default_model in models else models[0]
        config.providers[provider] = existing.model_copy(
            update={"default_model": default_model, "models": models}
        )
        atomic_write_text(self.path, _render_catalog(config))
        return False

    def _load(self) -> CatalogConfig:
        if not self.path.is_file():
            return CatalogConfig()
        try:
            with self.path.open("rb") as stream:
                return CatalogConfig.model_validate(tomllib.load(stream))
        except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
            raise ModelCatalogError(f"cannot update model catalog {self.path}: {exc}") from exc


def _normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL must be an HTTP or HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Base URL must not contain credentials, a query, or a fragment")
    matched = _RESOURCE_ENDPOINT_PATTERN.search(parsed.path)
    if matched is not None:
        root_path = parsed.path[: matched.start()] or "/"
        suggestion = parsed._replace(path=root_path, params="", query="", fragment="").geturl()
        suggestion = suggestion.rstrip("/")
        raise ValueError(
            "Base URL must be the API root because Forge appends /chat/completions; "
            f"use {suggestion}"
        )
    return base_url


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
