from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agent.config import Settings
from coding_agent.model_catalog import (
    ModelCatalog,
    ModelCatalogError,
    ModelSelectionStore,
)
from coding_agent.model_client import ModelClient
from coding_agent.model_runtime import ModelManager


def _write_catalog(path: Path) -> None:
    path.write_text(
        """
default_provider = "gemini"

[providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key_env = "GEMINI_API_KEY"
default_model = "gemini-flash"
models = ["gemini-flash", "gemini-pro"]
compatibility = "gemini"

[providers.deepseek]
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"
default_model = "deepseek-chat"
models = ["deepseek-chat"]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_catalog_resolves_provider_default_without_exposing_key(tmp_path: Path) -> None:
    path = tmp_path / "models.toml"
    _write_catalog(path)
    catalog = ModelCatalog(path=path, environ={"GEMINI_API_KEY": "top-secret"})

    selection = catalog.resolve("gemini")

    assert selection.provider == "gemini"
    assert selection.model == "gemini-flash"
    assert selection.compatibility == "gemini"
    assert selection.api_key == "top-secret"
    assert "top-secret" not in repr(selection)


def test_catalog_rejects_unknown_model_and_missing_key_without_leaking_secret(
    tmp_path: Path,
) -> None:
    path = tmp_path / "models.toml"
    _write_catalog(path)
    catalog = ModelCatalog(path=path, environ={"GEMINI_API_KEY": "top-secret"})

    with pytest.raises(ModelCatalogError, match="not configured"):
        catalog.resolve("gemini", "unknown")
    with pytest.raises(ModelCatalogError, match="DEEPSEEK_API_KEY") as captured:
        catalog.resolve("deepseek")

    assert "top-secret" not in str(captured.value)


def test_model_selection_store_persists_only_provider_and_model(tmp_path: Path) -> None:
    store = ModelSelectionStore(data_dir=tmp_path)

    store.save(provider="gemini", model="gemini-flash")

    assert store.load() is not None
    assert store.load().provider == "gemini"  # type: ignore[union-attr]
    assert store.load().model == "gemini-flash"  # type: ignore[union-attr]
    assert json.loads(store.path.read_text(encoding="utf-8")) == {
        "provider": "gemini",
        "model": "gemini-flash",
    }


def test_model_manager_switches_connection_and_persists_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "models.toml"
    _write_catalog(path)
    catalog = ModelCatalog(path=path, environ={"GEMINI_API_KEY": "new-secret"})
    replacement = object()
    monkeypatch.setattr("coding_agent.model_client.OpenAI", lambda **kwargs: replacement)
    client = ModelClient(model="old-model", api_key="old-secret", client=object())
    settings = Settings(
        cwd=tmp_path,
        data_dir=tmp_path,
        model={"name": "old-model", "api_key": "old-secret"},
    )
    state = ModelSelectionStore(data_dir=tmp_path)
    manager = ModelManager(
        client=client,
        settings=settings,
        catalog=catalog,
        state=state,
        provider="legacy",
    )

    selected = manager.switch("gemini", "gemini-pro")

    assert selected.model == "gemini-pro"
    assert manager.provider == "gemini"
    assert client.model == "gemini-pro"
    assert client.base_url == selected.base_url
    assert settings.model.name == "gemini-pro"
    assert state.load() is not None and state.load().provider == "gemini"


def test_model_manager_keeps_old_connection_when_reconfiguration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "models.toml"
    _write_catalog(path)
    catalog = ModelCatalog(path=path, environ={"GEMINI_API_KEY": "new-secret"})

    def fail(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("cannot create client")

    monkeypatch.setattr("coding_agent.model_client.OpenAI", fail)
    old_connection = object()
    client = ModelClient(model="old-model", api_key="old-secret", client=old_connection)
    settings = Settings(
        cwd=tmp_path,
        data_dir=tmp_path,
        model={"name": "old-model", "api_key": "old-secret"},
    )
    state = ModelSelectionStore(data_dir=tmp_path)
    manager = ModelManager(
        client=client,
        settings=settings,
        catalog=catalog,
        state=state,
        provider="legacy",
    )

    with pytest.raises(RuntimeError, match="cannot create client"):
        manager.switch("gemini")

    assert manager.provider == "legacy"
    assert client.model == "old-model"
    assert client._client is old_connection
    assert settings.model.name == "old-model"
    assert state.load() is None
