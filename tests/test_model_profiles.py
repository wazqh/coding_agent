from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from coding_agent.model_profiles import ModelProfileWriter, provider_api_key_env


def test_provider_api_key_env_is_deterministic() -> None:
    assert provider_api_key_env("OpenRouter") == "FORGE_PROVIDER_OPENROUTER_API_KEY"
    assert provider_api_key_env("local-proxy.v2") == "FORGE_PROVIDER_LOCAL_PROXY_V2_API_KEY"


def test_upsert_provider_preserves_existing_profiles_and_never_accepts_a_secret(
    tmp_path: Path,
) -> None:
    path = tmp_path / "models.toml"
    path.write_text(
        """
default_provider = "existing"

[providers.existing]
base_url = "https://example.test/v1"
api_key_env = "EXISTING_API_KEY"
default_model = "old-model"
models = ["old-model"]
compatibility = "openai"
""".lstrip(),
        encoding="utf-8",
    )
    writer = ModelProfileWriter(path)

    result = writer.upsert(
        provider="open-router",
        base_url="https://openrouter.ai/api/v1",
        model="vendor/model",
        compatibility="openai",
    )

    assert result.api_key_env == "FORGE_PROVIDER_OPEN_ROUTER_API_KEY"
    value = tomllib.loads(path.read_text(encoding="utf-8"))
    assert set(value["providers"]) == {"existing", "open-router"}
    assert value["providers"]["existing"]["default_model"] == "old-model"
    assert value["providers"]["open-router"] == {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "FORGE_PROVIDER_OPEN_ROUTER_API_KEY",
        "default_model": "vendor/model",
        "models": ["vendor/model"],
        "compatibility": "openai",
    }
    assert "secret" not in path.read_text(encoding="utf-8").lower()


def test_upsert_provider_rejects_invalid_names_and_urls(tmp_path: Path) -> None:
    writer = ModelProfileWriter(tmp_path / "models.toml")

    with pytest.raises(ValueError, match="provider"):
        writer.upsert(provider="bad name", base_url="https://example.test/v1", model="m")
    with pytest.raises(ValueError, match="Base URL"):
        writer.upsert(provider="valid", base_url="file:///tmp/model", model="m")


def test_upsert_existing_provider_preserves_and_deduplicates_models(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    path.write_text(
        """
default_provider = "gemini"

[providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
api_key_env = "GEMINI_API_KEY"
default_model = "gemini-2.5-flash"
models = ["gemini-2.5-flash", "gemini-2.5-pro"]
compatibility = "gemini"
""".lstrip(),
        encoding="utf-8",
    )

    writer = ModelProfileWriter(path)
    writer.upsert(
        provider="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-3.7-flash",
        compatibility="gemini",
    )
    writer.upsert(
        provider="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-2.5-pro",
        compatibility="gemini",
    )

    profile = tomllib.loads(path.read_text(encoding="utf-8"))["providers"]["gemini"]
    assert profile["default_model"] == "gemini-2.5-pro"
    assert profile["models"] == [
        "gemini-2.5-pro",
        "gemini-3.7-flash",
        "gemini-2.5-flash",
    ]
