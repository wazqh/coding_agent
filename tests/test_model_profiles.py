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
    assert result.credential_ref == "provider:open-router"
    value = tomllib.loads(path.read_text(encoding="utf-8"))
    assert set(value["providers"]) == {"existing", "open-router"}
    assert value["providers"]["existing"]["default_model"] == "old-model"
    assert value["providers"]["open-router"] == {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "FORGE_PROVIDER_OPEN_ROUTER_API_KEY",
        "credential_ref": "provider:open-router",
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


def test_upsert_provider_rejects_a_full_chat_completions_endpoint(tmp_path: Path) -> None:
    writer = ModelProfileWriter(tmp_path / "models.toml")

    with pytest.raises(
        ValueError,
        match=r"Base URL.*https://open.bigmodel.cn/api/paas/v4",
    ):
        writer.upsert(
            provider="glm",
            base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions/",
            model="glm-4.5",
        )


def test_delete_provider_preserves_other_profiles_and_refuses_the_last_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "models.toml"
    writer = ModelProfileWriter(path)
    writer.upsert(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-5",
    )
    writer.upsert(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )

    writer.delete("deepseek")

    value = tomllib.loads(path.read_text(encoding="utf-8"))
    assert set(value["providers"]) == {"openai"}
    assert value["default_provider"] == "openai"
    with pytest.raises(ValueError, match="last provider"):
        writer.delete("openai")


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


def test_update_model_replaces_only_the_selected_model(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    path.write_text(
        """
default_provider = "glm"

[providers.glm]
base_url = "https://open.bigmodel.cn/api/paas/v4"
api_key_env = "GLM_API_KEY"
default_model = "glm-5.3-flash"
models = ["glm-5.3-flash", "glm-5.2-flash"]
compatibility = "openai"
""".lstrip(),
        encoding="utf-8",
    )

    ModelProfileWriter(path).update_model(
        provider="glm",
        original_model="glm-5.2-flash",
        model="glm-5.2-air",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        compatibility="openai",
    )

    profile = tomllib.loads(path.read_text(encoding="utf-8"))["providers"]["glm"]
    assert profile["default_model"] == "glm-5.3-flash"
    assert profile["models"] == ["glm-5.3-flash", "glm-5.2-air"]


def test_delete_model_keeps_siblings_and_removes_the_provider_for_its_last_model(
    tmp_path: Path,
) -> None:
    path = tmp_path / "models.toml"
    writer = ModelProfileWriter(path)
    writer.upsert(provider="glm", base_url="https://example.test/v1", model="glm-a")
    writer.upsert(provider="glm", base_url="https://example.test/v1", model="glm-b")
    writer.upsert(provider="other", base_url="https://other.test/v1", model="other-a")

    assert writer.delete_model("glm", "glm-a") is False
    profile = tomllib.loads(path.read_text(encoding="utf-8"))["providers"]["glm"]
    assert profile["models"] == ["glm-b"]
    assert profile["default_model"] == "glm-b"

    assert writer.delete_model("glm", "glm-b") is True
    value = tomllib.loads(path.read_text(encoding="utf-8"))
    assert set(value["providers"]) == {"other"}
