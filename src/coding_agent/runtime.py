from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from coding_agent.config import ConfigError, Settings, load_settings
from coding_agent.controller import AgentController
from coding_agent.credentials import CredentialService, KeyringCredentialService
from coding_agent.memory import MemoryStore
from coding_agent.model_catalog import ModelCatalog, ModelSelectionStore
from coding_agent.model_client import Compatibility, ModelClient
from coding_agent.model_runtime import ModelManager
from coding_agent.project import load_agents_instructions
from coding_agent.safety.approval import ApprovalCallback, ApprovalPolicy
from coding_agent.session import SessionStore
from coding_agent.skills import SkillRegistry
from coding_agent.tools.base import EventSink
from coding_agent.tools.registry import default_registry
from coding_agent.workspace_settings import WorkspaceSettingsStore

ControllerFactory = Callable[[str | None], AgentController]


class RuntimeFactory:
    """Build frontend-neutral controllers over one configured local runtime."""

    def __init__(
        self,
        *,
        workspace: Path,
        data_dir: Path,
        permissions: str,
        trusted_project: bool,
        interactive: bool,
        model_name: str | None = None,
        event_sink: EventSink | None = None,
        approval_callback: ApprovalCallback | None = None,
        environ: Mapping[str, str] | None = None,
        credentials: CredentialService | None = None,
    ) -> None:
        if permissions not in {"prompt", "auto", "read-only"}:
            raise ConfigError("--permissions must be prompt, auto, or read-only")

        environment = dict(os.environ if environ is None else environ)
        resolved_workspace = workspace.expanduser().resolve()
        overlay = {"model": {"name": model_name}} if model_name else None
        self.settings: Settings = load_settings(
            resolved_workspace,
            trusted_project=trusted_project,
            cli=overlay,
            environ=environment,
            data_dir=data_dir,
        )
        self.settings.agent.capture_configured_max_steps()
        workspace_settings = WorkspaceSettingsStore(
            data_dir=data_dir,
            workspace=resolved_workspace,
        )
        workspace_overrides = workspace_settings.load()
        max_steps_override = workspace_overrides.max_steps
        if max_steps_override is not None:
            self.settings.agent.max_steps = max_steps_override
        self.verification_enabled = workspace_overrides.verification.enabled
        self.verification_agent_tdd = workspace_overrides.verification.agent_tdd
        self.verification_commands = tuple(workspace_overrides.verification.commands)

        self.credentials = credentials or KeyringCredentialService()
        self.catalog = ModelCatalog(
            path=data_dir / "models.toml",
            environ=environment,
            credentials=self.credentials,
        )
        self.model_state = ModelSelectionStore(data_dir=data_dir)
        active_model = self.model_state.load()
        self.provider = "legacy"
        compatibility: Compatibility = (
            "gemini"
            if self.settings.model.base_url
            and "generativelanguage.googleapis.com" in self.settings.model.base_url
            else "openai"
        )
        if self.catalog.providers():
            self.provider = (
                active_model.provider
                if active_model is not None and active_model.provider in self.catalog.providers()
                else self.catalog.default_provider or ""
            )
            selected_name = model_name
            if (
                selected_name is None
                and active_model is not None
                and active_model.provider == self.provider
            ):
                profile = self.catalog.config.providers[self.provider]
                if not profile.models or active_model.model in profile.models:
                    selected_name = active_model.model
            selected = self.catalog.resolve(self.provider, selected_name)
            if active_model is not None and (
                active_model.provider != selected.provider or active_model.model != selected.model
            ):
                self.model_state.save(provider=selected.provider, model=selected.model)
            self.settings.model.name = selected.model
            self.settings.model.base_url = selected.base_url
            self.settings.model.api_key = selected.api_key
            compatibility = selected.compatibility
        if not self.settings.model.api_key:
            raise ConfigError("OPENAI_API_KEY is not set")

        self.permissions = permissions
        self.trusted_project = trusted_project
        self.interactive = interactive
        self.event_sink = event_sink
        self.approval_callback = approval_callback
        self.model = ModelClient(
            model=self.settings.model.name,
            api_key=self.settings.model.api_key,
            base_url=self.settings.model.base_url,
            max_retries=self.settings.model.max_retries,
            compatibility=compatibility,
        )
        self.model_manager = ModelManager(
            client=self.model,
            settings=self.settings,
            catalog=self.catalog,
            state=self.model_state,
            provider=self.provider,
        )
        self.sessions = SessionStore(self.settings.data_dir)
        self.agents_instructions = (
            load_agents_instructions(self.settings.cwd) if trusted_project else ""
        )

    def create(self, session_id: str | None = None) -> AgentController:
        approval = ApprovalPolicy(
            self.permissions,
            interactive=self.interactive,
            callback=self.approval_callback if self.interactive else None,
        )
        memory = MemoryStore(
            data_dir=self.settings.data_dir,
            workspace=self.settings.cwd,
            enabled=self.settings.memory.enabled,
        )
        skills = SkillRegistry(workspace=self.settings.cwd)
        skills.discover(include_repo=self.trusted_project)
        return AgentController(
            settings=self.settings,
            model=self.model,
            tools=default_registry(),
            sessions=self.sessions,
            memory=memory,
            skills=skills,
            approval=approval,
            agents_instructions=self.agents_instructions,
            session_id=session_id,
            event_sink=self.event_sink,
            model_manager=self.model_manager,
            verification_commands=self.verification_commands,
            verification_enabled=self.verification_enabled,
            verification_agent_tdd=self.verification_agent_tdd,
        )

    def controller_factory(self) -> ControllerFactory:
        return self.create
