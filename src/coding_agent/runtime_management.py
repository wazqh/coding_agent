from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from coding_agent.model_profiles import ModelProfileWriter
from coding_agent.workspace_settings import WorkspaceSettingsStore

if TYPE_CHECKING:
    from coding_agent.controller import AgentController
    from coding_agent.runtime import RuntimeFactory

PermissionMode = Literal["prompt", "auto", "read-only"]


class LifecycleState(StrEnum):
    IDLE = "idle"
    REQUESTING = "requesting"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING_TOOL = "executing_tool"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StepSettings(_FrozenModel):
    current: int = Field(ge=12, le=100)
    configured_default: int = Field(ge=12, le=100)
    overridden: bool
    minimum: Literal[12] = 12
    maximum: Literal[100] = 100


class ModelSummary(_FrozenModel):
    provider: str
    id: str


class ModelProviderSummary(_FrozenModel):
    name: str
    default_model: str
    models: tuple[str, ...]
    active: bool


class ModelCatalogSnapshot(_FrozenModel):
    active: ModelSummary
    providers: tuple[ModelProviderSummary, ...]


class ProviderConfigurationResult(_FrozenModel):
    provider: str
    model: str
    api_key_env: str
    requires_restart: Literal[True] = True
    catalog: ModelCatalogSnapshot


class ContextSummary(_FrozenModel):
    estimated_tokens: int = Field(ge=0)
    context_window: int = Field(ge=1)
    percent_used: int = Field(ge=0)
    breakdown: dict[str, int] = Field(default_factory=dict)


class VerificationSummary(_FrozenModel):
    commands: tuple[str, ...] = ()


class MemorySummary(_FrozenModel):
    available: bool
    enabled: bool
    count: int = Field(ge=0)


class SkillsSummary(_FrozenModel):
    available: bool
    count: int = Field(ge=0)
    active: tuple[str, ...] = ()


class ResourceSummary(_FrozenModel):
    project_resources_loaded: bool
    memory: MemorySummary
    skills: SkillsSummary


class PlanStep(_FrozenModel):
    step: str
    status: str


class RuntimeSnapshot(_FrozenModel):
    workspace: str
    workspace_name: str
    session_id: str
    lifecycle: LifecycleState
    permissions: PermissionMode
    session_grants: int = Field(ge=0)
    steps: StepSettings
    model: ModelSummary
    context: ContextSummary
    verification: VerificationSummary
    resources: ResourceSummary
    plan: tuple[PlanStep, ...] = ()


class MemorySnapshot(_FrozenModel):
    enabled: bool
    items: tuple[dict[str, object], ...]


class SkillsSnapshot(_FrozenModel):
    items: tuple[dict[str, object], ...]
    active: tuple[str, ...]
    diagnostics: tuple[str, ...]


class CompactResult(_FrozenModel):
    changed: bool
    before_tokens: int = Field(ge=0)
    after_tokens: int = Field(ge=0)
    transcript_retained: Literal[True] = True


class RuntimeManagement:
    """Frontend-neutral, allowlisted management surface over the local runtime."""

    def __init__(
        self,
        *,
        runtime: RuntimeFactory,
        controller_provider: Callable[[], AgentController],
        workspace_settings: WorkspaceSettingsStore,
    ) -> None:
        self.runtime = runtime
        self._controller_provider = controller_provider
        self.workspace_settings = workspace_settings
        self._lifecycle = LifecycleState.IDLE

    def set_lifecycle(self, lifecycle: LifecycleState) -> None:
        self._lifecycle = lifecycle

    def snapshot(self) -> RuntimeSnapshot:
        controller = self._controller_provider()
        settings = controller.settings
        agent = settings.agent
        workspace = settings.cwd.resolve()
        override = self.workspace_settings.load().max_steps
        memory = controller.memory
        skills = controller.skills
        tokens = max(0, int(controller.last_context_tokens))
        breakdown = controller.context_breakdown()
        context_window = max(1, int(agent.context_window))
        raw_plan = getattr(controller.working, "plan", [])
        plan = tuple(
            PlanStep(step=str(item.get("step", "")), status=str(item.get("status", "pending")))
            for item in raw_plan
            if isinstance(item, dict)
        )
        skill_catalog = [] if skills is None else skills.catalog()
        skill_active = () if skills is None else tuple(sorted(skills.active))
        permission = cast(PermissionMode, controller.approval.mode)
        return RuntimeSnapshot(
            workspace=str(workspace),
            workspace_name=workspace.name or str(workspace),
            session_id=controller.session_id,
            lifecycle=self._lifecycle,
            permissions=permission,
            session_grants=controller.approval.session_grant_count,
            steps=StepSettings(
                current=agent.max_steps,
                configured_default=agent.configured_max_steps,
                overridden=override is not None,
            ),
            model=ModelSummary(
                provider=(
                    controller.model_manager.provider
                    if controller.model_manager is not None
                    else self.runtime.provider
                ),
                id=settings.model.name,
            ),
            context=ContextSummary(
                estimated_tokens=tokens,
                context_window=context_window,
                percent_used=round(tokens * 100 / context_window),
                breakdown=breakdown,
            ),
            verification=VerificationSummary(
                commands=tuple(self.workspace_settings.load().verification.commands)
            ),
            resources=ResourceSummary(
                project_resources_loaded=self.runtime.trusted_project,
                memory=MemorySummary(
                    available=memory is not None,
                    enabled=bool(memory is not None and memory.enabled),
                    count=0 if memory is None else len(memory.list()),
                ),
                skills=SkillsSummary(
                    available=skills is not None,
                    count=len(skill_catalog),
                    active=skill_active,
                ),
            ),
            plan=plan,
        )

    def set_permissions(self, mode: str) -> RuntimeSnapshot:
        if mode not in {"prompt", "auto", "read-only"}:
            raise ValueError("permissions must be prompt, auto, or read-only")
        controller = self._controller_provider()
        controller.approval.set_mode(mode)
        self.runtime.permissions = mode
        return self.snapshot()

    def set_steps(self, value: int) -> RuntimeSnapshot:
        self.workspace_settings.set_max_steps(value)
        self._controller_provider().settings.agent.max_steps = value
        return self.snapshot()

    def reset_steps(self) -> RuntimeSnapshot:
        controller = self._controller_provider()
        self.workspace_settings.reset_max_steps()
        controller.settings.agent.max_steps = controller.settings.agent.configured_max_steps
        return self.snapshot()

    def set_verification_commands(self, commands: list[str]) -> RuntimeSnapshot:
        self.workspace_settings.set_verification_commands(commands)
        normalized = tuple(self.workspace_settings.load().verification.commands)
        self.runtime.verification_commands = normalized
        self._controller_provider().verification_commands = normalized
        return self.snapshot()

    def reset_verification_commands(self) -> RuntimeSnapshot:
        self.workspace_settings.reset_verification_commands()
        self.runtime.verification_commands = ()
        self._controller_provider().verification_commands = ()
        return self.snapshot()

    def model_catalog(self) -> ModelCatalogSnapshot:
        controller = self._controller_provider()
        active_provider = (
            controller.model_manager.provider
            if controller.model_manager is not None
            else self.runtime.provider
        )
        providers = tuple(
            ModelProviderSummary(
                name=name,
                default_model=profile.default_model,
                models=tuple(profile.models or [profile.default_model]),
                active=name == active_provider,
            )
            for name, profile in self.runtime.catalog.config.providers.items()
        )
        if not providers:
            providers = (
                ModelProviderSummary(
                    name=active_provider,
                    default_model=controller.settings.model.name,
                    models=(controller.settings.model.name,),
                    active=True,
                ),
            )
        return ModelCatalogSnapshot(
            active=ModelSummary(provider=active_provider, id=controller.settings.model.name),
            providers=providers,
        )

    def select_model(self, provider: str, model_id: str | None = None) -> ModelCatalogSnapshot:
        controller = self._controller_provider()
        manager = controller.model_manager
        if manager is None:
            raise ValueError("model management is unavailable")
        previous = (manager.provider, controller.settings.model.name)
        selected = manager.switch(provider, model_id)
        self.runtime.provider = manager.provider
        if previous != (selected.provider, selected.model):
            controller.sessions.append(
                controller.session_id,
                "configuration",
                {"provider": selected.provider, "model": selected.model},
            )
        return self.model_catalog()

    def reload_models(self) -> ModelCatalogSnapshot:
        self.runtime.catalog.reload()
        return self.model_catalog()

    def upsert_model_provider(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        compatibility: Literal["openai", "gemini"] = "openai",
    ) -> ProviderConfigurationResult:
        result = ModelProfileWriter(self.runtime.catalog.path).upsert(
            provider=provider,
            base_url=base_url,
            model=model,
            compatibility=compatibility,
        )
        self.runtime.model_state.save(provider=provider, model=model)
        controller = self._controller_provider()
        controller.sessions.append(
            controller.session_id,
            "configuration",
            {"provider": result.provider, "model": result.model},
        )
        self.runtime.catalog.reload()
        return ProviderConfigurationResult(
            provider=result.provider,
            model=result.model,
            api_key_env=result.api_key_env,
            catalog=self.model_catalog(),
        )

    def memory_snapshot(self) -> MemorySnapshot:
        memory = self._controller_provider().memory
        if memory is None:
            raise ValueError("memory is unavailable")
        items = tuple(
            cast(dict[str, object], record.model_dump(mode="json"))
            for record in memory.list(include_disabled=True)
        )
        return MemorySnapshot(enabled=memory.enabled, items=items)

    def set_memory_enabled(self, enabled: bool) -> MemorySnapshot:
        controller = self._controller_provider()
        if controller.memory is None:
            raise ValueError("memory is unavailable")
        controller.memory.enabled = enabled
        controller.settings.memory.enabled = enabled
        return self.memory_snapshot()

    def remember(self, content: str) -> MemorySnapshot:
        controller = self._controller_provider()
        if controller.memory is None:
            raise ValueError("memory is unavailable")
        controller.memory.remember(content=content, session_id=controller.session_id)
        return self.memory_snapshot()

    def forget_memory(self, memory_id: str) -> MemorySnapshot:
        controller = self._controller_provider()
        if controller.memory is None:
            raise ValueError("memory is unavailable")
        if not controller.memory.forget(memory_id):
            raise ValueError("memory was not found or is already disabled")
        return self.memory_snapshot()

    def clear_memory(self) -> MemorySnapshot:
        memory = self._controller_provider().memory
        if memory is None:
            raise ValueError("memory is unavailable")
        memory.clear()
        return self.memory_snapshot()

    def skills_snapshot(self) -> SkillsSnapshot:
        skills = self._controller_provider().skills
        if skills is None:
            raise ValueError("skills are unavailable")
        return SkillsSnapshot(
            items=tuple(cast(dict[str, object], item) for item in skills.catalog()),
            active=tuple(sorted(skills.active)),
            diagnostics=tuple(skills.diagnostics),
        )

    def set_skill_enabled(self, name: str, enabled: bool) -> SkillsSnapshot:
        self._controller_provider().set_skill_enabled(name, enabled)
        return self.skills_snapshot()

    def reload_skills(self) -> SkillsSnapshot:
        skills = self._controller_provider().skills
        if skills is None:
            raise ValueError("skills are unavailable")
        skills.discover(include_repo=self.runtime.trusted_project)
        return self.skills_snapshot()

    def compact_context(self) -> CompactResult:
        controller = self._controller_provider()
        before = controller.last_context_tokens
        summary = controller.manual_compact()
        return CompactResult(
            changed=bool(summary),
            before_tokens=before,
            after_tokens=controller.last_context_tokens,
        )
