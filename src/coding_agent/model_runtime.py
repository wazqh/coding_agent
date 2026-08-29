from __future__ import annotations

from coding_agent.config import Settings
from coding_agent.model_catalog import ModelCatalog, ModelSelection, ModelSelectionStore
from coding_agent.model_client import ModelClient


class ModelManager:
    def __init__(
        self,
        *,
        client: ModelClient,
        settings: Settings,
        catalog: ModelCatalog,
        state: ModelSelectionStore,
        provider: str,
    ) -> None:
        self.client = client
        self.settings = settings
        self.catalog = catalog
        self.state = state
        self.provider = provider

    def switch(self, provider: str, model: str | None = None) -> ModelSelection:
        selected = self.catalog.resolve(provider, model)
        self.client.reconfigure(
            model=selected.model,
            api_key=selected.api_key,
            base_url=selected.base_url,
            compatibility=selected.compatibility,
            max_retries=self.settings.model.max_retries,
        )
        self.settings.model.name = selected.model
        self.settings.model.base_url = selected.base_url
        self.settings.model.api_key = selected.api_key
        self.provider = selected.provider
        self.state.save(provider=selected.provider, model=selected.model)
        return selected

    def switch_model(self, model: str) -> ModelSelection:
        if self.provider in self.catalog.providers():
            return self.switch(self.provider, model)
        api_key = self.settings.model.api_key
        if not api_key:
            raise ValueError("current model API key is unavailable")
        self.client.reconfigure(
            model=model,
            api_key=api_key,
            base_url=self.settings.model.base_url,
            compatibility=self.client.compatibility,
            max_retries=self.settings.model.max_retries,
        )
        self.settings.model.name = model
        return ModelSelection(
            provider=self.provider,
            model=model,
            base_url=self.settings.model.base_url,
            api_key=api_key,
            compatibility=self.client.compatibility,
        )

    def reload(self) -> None:
        self.catalog.reload()
