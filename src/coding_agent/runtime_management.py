from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from contextlib import suppress
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from coding_agent.config import MAX_AGENT_STEPS, MIN_AGENT_STEPS
from coding_agent.model_profiles import ModelProfileWriter
from coding_agent.skills import VALID_NAME
from coding_agent.verification import (
    VerificationContract,
    VerificationMode,
    VerificationProcedure,
)
from coding_agent.workspace_settings import VerificationCheck, WorkspaceSettingsStore

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
    current: int = Field(ge=MIN_AGENT_STEPS, le=MAX_AGENT_STEPS)
    configured_default: int = Field(ge=MIN_AGENT_STEPS, le=MAX_AGENT_STEPS)
    overridden: bool
    minimum: Literal[30] = MIN_AGENT_STEPS
    maximum: Literal[999] = MAX_AGENT_STEPS


class ModelSummary(_FrozenModel):
    provider: str
    id: str


class ModelProviderSummary(_FrozenModel):
    name: str
    base_url: str | None
    default_model: str
    models: tuple[str, ...]
    compatibility: Literal["openai", "gemini"]
    managed: bool = True
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


class ModelProbeResult(_FrozenModel):
    ok: bool
    category: Literal["ready", "authentication", "model", "rate_limit", "network", "provider"]
    message: str


class ContextSummary(_FrozenModel):
    estimated_tokens: int = Field(ge=0)
    context_window: int = Field(ge=1)
    percent_used: int = Field(ge=0)
    breakdown: dict[str, int] = Field(default_factory=dict)


class VerificationSuggestion(_FrozenModel):
    id: str
    label: str
    kind: Literal["test", "build", "lint", "typecheck", "custom"]
    command: str
    cwd: str
    target_paths: tuple[str, ...]
    scope: Literal["focused", "full_project"]


class VerificationSummary(_FrozenModel):
    mode: VerificationMode = VerificationMode.OFF
    enabled: bool = False
    agent_tdd: bool = False
    checks: tuple[VerificationCheck, ...] = ()
    procedures: tuple[VerificationProcedure, ...] = ()
    commands: tuple[str, ...] = ()
    suggested_commands: tuple[str, ...] = ()
    suggestions: tuple[VerificationSuggestion, ...] = ()
    workspace_templates: tuple[VerificationCheck, ...] = ()


def _verification_suggestions(workspace: Path) -> tuple[VerificationSuggestion, ...]:
    """Return conservative, project-derived verification commands for the GUI."""

    suggestions: list[VerificationSuggestion] = []
    ignored_directories = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }

    def project_roots() -> tuple[Path, ...]:
        roots = [workspace]
        pending: list[tuple[Path, int]] = [(workspace, 0)]
        while pending and len(roots) < 64:
            parent, depth = pending.pop(0)
            if depth >= 2:
                continue
            try:
                children = sorted(parent.iterdir(), key=lambda path: path.name.casefold())
            except OSError:
                continue
            for child in children:
                if len(roots) >= 64:
                    break
                if (
                    not child.is_dir()
                    or child.is_symlink()
                    or child.name.startswith(".")
                    or child.name in ignored_directories
                ):
                    continue
                roots.append(child)
                pending.append((child, depth + 1))
        return tuple(roots)

    roots = project_roots()

    def add(
        *,
        label: str,
        kind: Literal["test", "build", "lint", "typecheck", "custom"],
        command: str,
        cwd: str = ".",
    ) -> None:
        if any(item.command == command and item.cwd == cwd for item in suggestions):
            return
        if len(suggestions) >= 8:
            return
        focused = cwd != "."
        slug = re.sub(r"[^a-z0-9]+", "-", f"{cwd}-{kind}".casefold()).strip("-")
        suggestions.append(
            VerificationSuggestion(
                id=f"suggested-{slug or kind}",
                label=label,
                kind=kind,
                command=command,
                cwd=cwd,
                target_paths=(cwd,) if focused else (".",),
                scope="focused" if focused else "full_project",
            )
        )

    for root in roots:
        cwd = root.relative_to(workspace).as_posix() or "."
        pyproject = root / "pyproject.toml"
        pyproject_text = ""
        with suppress(OSError):
            if pyproject.is_file() and pyproject.stat().st_size <= 2 * 1024 * 1024:
                pyproject_text = pyproject.read_text(encoding="utf-8")
        python_label = "Python tests" if cwd == "." else f"{root.name} tests"
        if (
            (root / "pytest.ini").is_file()
            or (root / "tox.ini").is_file()
            or (root / "tests").is_dir()
            or "[tool.pytest" in pyproject_text
        ):
            add(
                label=python_label,
                kind="test",
                command="python -m pytest -q",
                cwd=cwd,
            )
        if (root / "ruff.toml").is_file() or "[tool.ruff" in pyproject_text:
            add(label=f"{root.name} Ruff", kind="lint", command="python -m ruff check .", cwd=cwd)
        if (root / "mypy.ini").is_file() or "[tool.mypy" in pyproject_text:
            add(label=f"{root.name} Mypy", kind="typecheck", command="python -m mypy", cwd=cwd)

    package_files = [root / "package.json" for root in roots]
    for package_file in package_files[:32]:
        try:
            if package_file.stat().st_size > 2 * 1024 * 1024:
                continue
            payload = json.loads(package_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        scripts = payload.get("scripts") if isinstance(payload, dict) else None
        if not isinstance(scripts, dict):
            continue
        relative_parent = package_file.parent.relative_to(workspace)
        cwd = relative_parent.as_posix()
        if isinstance(scripts.get("test"), str):
            add(label=f"{package_file.parent.name} tests", kind="test", command="npm test", cwd=cwd)
        if isinstance(scripts.get("build"), str):
            add(
                label=f"{package_file.parent.name} build",
                kind="build",
                command="npm run build",
                cwd=cwd,
            )

    if (workspace / "Cargo.toml").is_file():
        add(label="Cargo tests", kind="test", command="cargo test")
    if (workspace / "go.mod").is_file():
        add(label="Go tests", kind="test", command="go test ./...")
    return tuple(suggestions)


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


class SkillDraft(_FrozenModel):
    name: str
    description: str
    instructions: str
    generated_by: Literal["model", "template"]


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
        contract = getattr(controller, "verification_contract", VerificationContract())
        workspace_templates = self.workspace_settings.load().verification.checks
        suggestions = _verification_suggestions(workspace)
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
                mode=contract.mode,
                enabled=contract.enabled,
                agent_tdd=contract.agent_tdd,
                checks=tuple(contract.checks),
                procedures=tuple(contract.procedures),
                commands=tuple(contract.commands),
                suggested_commands=tuple(item.command for item in suggestions),
                suggestions=suggestions,
                workspace_templates=tuple(workspace_templates),
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
        checks = [
            VerificationCheck(
                id=f"legacy-{index}",
                label=f"Verification {index}",
                command=command,
            )
            for index, command in enumerate(commands, start=1)
        ]
        return self.set_verification_contract(
            mode=VerificationMode.CHECKS if checks else VerificationMode.OFF,
            checks=checks,
            procedures=[],
        )

    def set_verification(
        self,
        *,
        enabled: bool,
        agent_tdd: bool,
        commands: list[str],
    ) -> RuntimeSnapshot:
        checks = [
            VerificationCheck(
                id=f"legacy-{index}",
                label=f"Verification {index}",
                command=command,
            )
            for index, command in enumerate(commands, start=1)
        ]
        mode = (
            VerificationMode.AGENT_TDD
            if enabled and agent_tdd
            else VerificationMode.CHECKS
            if enabled
            else VerificationMode.OFF
        )
        return self.set_verification_contract(mode=mode, checks=checks, procedures=[])

    def set_verification_checks(
        self,
        *,
        enabled: bool,
        agent_tdd: bool,
        checks: Sequence[VerificationCheck | dict[str, object]],
    ) -> RuntimeSnapshot:
        mode = (
            VerificationMode.AGENT_TDD
            if enabled and agent_tdd
            else VerificationMode.CHECKS
            if enabled
            else VerificationMode.OFF
        )
        return self.set_verification_contract(mode=mode, checks=checks, procedures=[])

    def set_verification_contract(
        self,
        *,
        mode: VerificationMode | str,
        checks: Sequence[VerificationCheck | dict[str, object]],
        procedures: Sequence[VerificationProcedure | dict[str, object]],
    ) -> RuntimeSnapshot:
        contract = VerificationContract(
            mode=VerificationMode(mode),
            checks=[VerificationCheck.model_validate(check) for check in checks],
            procedures=[VerificationProcedure.model_validate(item) for item in procedures],
        )
        controller = self._controller_provider()
        controller.set_verification_contract(contract)
        self.runtime.verification_enabled = contract.enabled
        self.runtime.verification_agent_tdd = contract.agent_tdd
        self.runtime.verification_commands = tuple(contract.commands)
        self.runtime.verification_checks = tuple(contract.checks)
        return self.snapshot()

    def reset_verification_commands(self) -> RuntimeSnapshot:
        return self.set_verification_contract(
            mode=VerificationMode.OFF,
            checks=[],
            procedures=[],
        )

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
                base_url=profile.base_url,
                default_model=profile.default_model,
                models=tuple(profile.models or [profile.default_model]),
                compatibility=profile.compatibility,
                active=name == active_provider,
            )
            for name, profile in self.runtime.catalog.config.providers.items()
        )
        if not providers:
            providers = (
                ModelProviderSummary(
                    name=active_provider,
                    base_url=None,
                    default_model=controller.settings.model.name,
                    models=(controller.settings.model.name,),
                    compatibility="openai",
                    managed=False,
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

    def delete_model_provider(self, provider: str) -> ModelCatalogSnapshot:
        controller = self._controller_provider()
        active_provider = (
            controller.model_manager.provider
            if controller.model_manager is not None
            else self.runtime.provider
        )
        selected = self.runtime.model_state.load()
        if provider == active_provider or (selected is not None and selected.provider == provider):
            raise ValueError("cannot delete the active provider; switch models first")
        ModelProfileWriter(self.runtime.catalog.path).delete(provider)
        self.runtime.catalog.reload()
        return self.model_catalog()

    def delete_model(self, provider: str, model: str) -> ModelCatalogSnapshot:
        controller = self._controller_provider()
        active_provider = (
            controller.model_manager.provider
            if controller.model_manager is not None
            else self.runtime.provider
        )
        if provider == active_provider and model == controller.settings.model.name:
            raise ValueError("cannot delete the active model; switch models first")
        ModelProfileWriter(self.runtime.catalog.path).delete_model(provider, model)
        self.runtime.catalog.reload()
        return self.model_catalog()

    def update_model(
        self,
        *,
        provider: str,
        original_model: str,
        model: str,
        base_url: str,
        compatibility: Literal["openai", "gemini"] = "openai",
    ) -> ModelCatalogSnapshot:
        controller = self._controller_provider()
        active_provider = (
            controller.model_manager.provider
            if controller.model_manager is not None
            else self.runtime.provider
        )
        editing_active = (
            provider == active_provider and original_model == controller.settings.model.name
        )
        ModelProfileWriter(self.runtime.catalog.path).update_model(
            provider=provider,
            original_model=original_model,
            model=model,
            base_url=base_url,
            compatibility=compatibility,
        )
        if editing_active:
            self.runtime.model_state.save(provider=provider, model=model)
            controller.settings.model.name = model
            controller.sessions.append(
                controller.session_id,
                "configuration",
                {"provider": provider, "model": model},
            )
        self.runtime.catalog.reload()
        return self.model_catalog()

    def probe_model(self) -> ModelProbeResult:
        events = self.runtime.model.stream(
            [{"role": "user", "content": "Reply with OK."}],
            [],
        )
        for event in events:
            if getattr(event, "type", "") != "error":
                continue
            raw = str(getattr(event, "error", ""))
            lowered = raw.casefold()
            if "401" in lowered or "api key" in lowered or "unauth" in lowered:
                return ModelProbeResult(
                    ok=False,
                    category="authentication",
                    message="API Key 无效，或密钥与服务地域不匹配。",
                )
            if "404" in lowered or ("model" in lowered and "not found" in lowered):
                return ModelProbeResult(
                    ok=False,
                    category="model",
                    message="Model ID 不存在，或当前账号无权访问该模型。",
                )
            if "429" in lowered or ("rate" in lowered and "limit" in lowered):
                return ModelProbeResult(
                    ok=False,
                    category="rate_limit",
                    message="服务商当前触发限流，请稍后重试。",
                )
            if "connect" in lowered or "timeout" in lowered or "network" in lowered:
                return ModelProbeResult(
                    ok=False,
                    category="network",
                    message="无法连接模型服务，请检查 Base URL、网络和代理设置。",
                )
            return ModelProbeResult(
                ok=False,
                category="provider",
                message="模型服务拒绝了兼容性探测，请检查供应商配置。",
            )
        return ModelProbeResult(ok=True, category="ready", message="连接成功，模型可以响应。")

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

    def draft_skill(self, *, requirement: str, template: str) -> SkillDraft:
        requirement = requirement.strip()
        if not requirement or len(requirement) > 4000:
            raise ValueError("skill requirement must contain 1-4000 characters")
        fallback = self._fallback_skill_draft(requirement=requirement, template=template)
        controller = self._controller_provider()
        prompt = (
            "Create a concise reusable SKILL.md draft from the user's requirement. "
            "Return one JSON object only with string fields name, description, and instructions. "
            "name must match ^[a-z0-9][a-z0-9_-]{0,63}$. instructions must be Markdown, "
            "must describe triggers, a concrete workflow, safety boundaries, and expected output. "
            "Do not include YAML frontmatter or hidden reasoning.\n\n"
            f"Template category: {template}\nUser requirement: {requirement}"
        )
        chunks: list[str] = []
        failed = False
        for event in controller.model.stream(
            [
                {"role": "system", "content": "You write reviewable Forge Coding Agent skills."},
                {"role": "user", "content": prompt},
            ],
            [],
        ):
            if event.type == "text_delta" and event.text:
                chunks.append(event.text)
            elif event.type == "error":
                failed = True
        if failed:
            return fallback
        try:
            raw = "".join(chunks)
            start = raw.index("{")
            end = raw.rindex("}") + 1
            value = json.loads(raw[start:end])
            name = str(value["name"]).strip()
            description = str(value["description"]).strip()
            instructions = str(value["instructions"]).strip()
            if (
                not VALID_NAME.fullmatch(name)
                or not description
                or len(description) > 1000
                or not instructions
            ):
                return fallback
            return SkillDraft(
                name=name,
                description=description,
                instructions=instructions,
                generated_by="model",
            )
        except (KeyError, TypeError, ValueError):
            return fallback

    @staticmethod
    def _fallback_skill_draft(*, requirement: str, template: str) -> SkillDraft:
        names = {
            "review": "code-review-helper",
            "testing": "test-repair-helper",
            "documentation": "documentation-helper",
        }
        labels = {
            "review": "Review code changes against the stated project rules.",
            "testing": "Run focused checks and repair reproducible failures.",
            "documentation": "Maintain accurate, structured project documentation.",
        }
        name = names.get(template, "custom-workflow")
        description = labels.get(template, requirement[:160])
        instructions = (
            "# Purpose\n\n"
            f"{requirement}\n\n"
            "# Workflow\n\n"
            "1. Read the applicable project instructions and relevant files.\n"
            "2. Confirm the requested scope and identify safety or approval boundaries.\n"
            "3. Perform the smallest complete workflow that satisfies the request.\n"
            "4. Verify the result and report concrete evidence, limitations, "
            "and follow-up work.\n\n"
            "# Safety\n\n"
            "Stay within the active workspace, never expose secrets, and request approval for "
            "operations covered by the runtime safety policy.\n"
        )
        return SkillDraft(
            name=name,
            description=description,
            instructions=instructions,
            generated_by="template",
        )

    def create_skill(
        self,
        *,
        scope: Literal["user", "repo"],
        name: str,
        description: str,
        instructions: str,
    ) -> SkillsSnapshot:
        if scope == "repo" and not self.runtime.trusted_project:
            raise ValueError("project skills require a trusted workspace")
        skills = self._controller_provider().skills
        if skills is None:
            raise ValueError("skills are unavailable")
        skills.create(
            scope=scope,
            name=name,
            description=description,
            instructions=instructions,
        )
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
