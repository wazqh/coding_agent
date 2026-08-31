from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

import coding_agent.workspace_settings as workspace_settings
from coding_agent.events import ModelStreamEvent
from coding_agent.model_catalog import ModelCatalog, ModelSelectionStore
from coding_agent.runtime_management import LifecycleState, RuntimeManagement
from coding_agent.safety.approval import ApprovalPolicy, ApprovalRequest
from coding_agent.session import SessionStore
from coding_agent.skills import SkillRegistry
from coding_agent.verification import VerificationContract, VerificationMode, VerificationProcedure
from coding_agent.workspace_settings import WorkspaceSettingsStore


def _management(tmp_path: Path) -> tuple[RuntimeManagement, SimpleNamespace]:
    data_dir = tmp_path / ".data"
    settings = SimpleNamespace(
        cwd=tmp_path,
        agent=SimpleNamespace(
            max_steps=40,
            configured_max_steps=40,
            context_window=32_768,
        ),
        model=SimpleNamespace(
            name="gemini-flash",
            api_key="must-never-leave-the-runtime",
            base_url="https://example.invalid/v1?token=secret",
        ),
    )
    controller = SimpleNamespace(
        session_id="a" * 24,
        settings=settings,
        approval=ApprovalPolicy("prompt"),
        last_context_tokens=8_192,
        working=SimpleNamespace(
            plan=[{"step": "Inspect", "status": "completed"}],
            active_skills=["review"],
        ),
        memory=SimpleNamespace(enabled=True, list=lambda: [object(), object()]),
        skills=SimpleNamespace(catalog=lambda: [{"name": "review"}], active={"review"}),
        model_manager=None,
        sessions=SessionStore(data_dir),
        verification_commands=(),
        verification_checks=(),
        verification_enabled=False,
        verification_agent_tdd=False,
        verification_contract=VerificationContract(),
        context_breakdown=lambda: {
            "system_and_project": 1024,
            "conversation_and_results": 4096,
            "tool_schemas": 2048,
            "other": 1024,
        },
    )
    controller.sessions.append(
        controller.session_id,
        "session",
        {"workspace": str(tmp_path), "model": "gemini-flash"},
    )

    def set_verification_contract(contract: VerificationContract) -> VerificationContract:
        controller.verification_contract = contract
        controller.verification_checks = tuple(contract.checks)
        controller.verification_commands = tuple(contract.commands)
        controller.verification_enabled = contract.enabled
        controller.verification_agent_tdd = contract.agent_tdd
        controller.sessions.append(
            controller.session_id,
            "verification_config",
            contract.model_dump(mode="json"),
        )
        return contract

    controller.set_verification_contract = set_verification_contract
    runtime = SimpleNamespace(
        settings=settings,
        provider="gemini",
        trusted_project=True,
        catalog=ModelCatalog(path=data_dir / "models.toml", environ={}),
        model_state=ModelSelectionStore(data_dir=data_dir),
    )
    management = RuntimeManagement(
        runtime=runtime,
        controller_provider=lambda: controller,
        workspace_settings=WorkspaceSettingsStore(
            data_dir=data_dir,
            workspace=tmp_path,
        ),
    )
    return management, controller


def test_runtime_snapshot_reports_tui_status_without_secrets(tmp_path: Path) -> None:
    management, _ = _management(tmp_path)

    snapshot = management.snapshot()

    assert snapshot.workspace == str(tmp_path.resolve())
    assert snapshot.session_id == "a" * 24
    assert snapshot.lifecycle is LifecycleState.IDLE
    assert snapshot.model.provider == "gemini"
    assert snapshot.model.id == "gemini-flash"
    assert snapshot.permissions == "prompt"
    assert snapshot.steps.minimum == 30
    assert snapshot.steps.maximum == 999
    assert snapshot.steps.current == 40
    assert snapshot.steps.overridden is False
    assert snapshot.verification.commands == ()
    assert snapshot.context.percent_used == 25
    assert snapshot.resources.memory.count == 2
    assert snapshot.resources.skills.active == ("review",)
    serialized = snapshot.model_dump_json().casefold()
    assert "api_key" not in serialized
    assert "must-never" not in serialized
    assert "token=secret" not in serialized


def test_permissions_change_revokes_session_grants(tmp_path: Path) -> None:
    management, controller = _management(tmp_path)
    controller.approval._session_grants.add(
        ApprovalRequest(action="write", subject="demo.py", summary="edit").fingerprint
    )

    snapshot = management.set_permissions("auto")

    assert snapshot.permissions == "auto"
    assert controller.approval.session_grant_count == 0


def test_steps_are_project_scoped_and_reset_to_configured_default(tmp_path: Path) -> None:
    management, controller = _management(tmp_path)

    changed = management.set_steps(40)

    assert changed.steps.current == 40
    assert changed.steps.overridden is True
    assert controller.settings.agent.max_steps == 40
    assert management.workspace_settings.load().max_steps == 40

    reset = management.reset_steps()

    assert reset.steps.current == 40
    assert reset.steps.overridden is False
    assert management.workspace_settings.load().max_steps is None


def test_verification_commands_are_session_scoped_and_update_the_active_controller(
    tmp_path: Path,
) -> None:
    management, controller = _management(tmp_path)

    changed = management.set_verification_commands(
        ["python -m pytest -q", "python -m ruff check ."]
    )

    assert changed.verification.commands == (
        "python -m pytest -q",
        "python -m ruff check .",
    )
    assert controller.verification_commands == changed.verification.commands
    assert management.workspace_settings.load().verification.commands == []
    records = controller.sessions.replay(controller.session_id)
    assert records[-1]["type"] == "verification_config"

    reset = management.reset_verification_commands()

    assert reset.verification.commands == ()
    assert controller.verification_commands == ()


def test_verification_mode_updates_runtime_and_controller(tmp_path: Path) -> None:
    management, controller = _management(tmp_path)

    changed = management.set_verification(
        enabled=True,
        agent_tdd=True,
        commands=["python -m pytest -q"],
    )

    assert changed.verification.enabled is True
    assert changed.verification.agent_tdd is True
    assert changed.verification.commands == ("python -m pytest -q",)
    assert controller.verification_enabled is True
    assert controller.verification_agent_tdd is True


def test_empty_agent_tdd_and_manual_procedures_are_valid_session_configuration(
    tmp_path: Path,
) -> None:
    management, controller = _management(tmp_path)

    changed = management.set_verification_contract(
        mode=VerificationMode.AGENT_TDD,
        checks=[],
        procedures=[
            VerificationProcedure(
                id="dependency-regression",
                instruction="After dependencies change, rerun the existing rules.",
            )
        ],
    )

    assert changed.verification.mode is VerificationMode.AGENT_TDD
    assert changed.verification.checks == ()
    assert changed.verification.procedures[0].id == "dependency-regression"
    assert controller.verification_contract.mode is VerificationMode.AGENT_TDD
    assert management.workspace_settings.load().verification.enabled is False


def test_structured_verification_checks_are_exposed_to_runtime_and_controller(
    tmp_path: Path,
) -> None:
    management, controller = _management(tmp_path)

    changed = management.set_verification_checks(
        enabled=True,
        agent_tdd=True,
        checks=[
            workspace_settings.VerificationCheck(
                id="web-tests",
                label="Web tests",
                kind="test",
                command="npm test",
                cwd="web",
                timeout_seconds=180,
            )
        ],
    )

    assert changed.verification.checks[0].cwd == "web"
    assert changed.verification.checks[0].command == "npm test"
    assert controller.verification_checks[0].cwd == "web"
    assert controller.verification_commands == ("npm test",)


def test_runtime_suggests_structured_verification_rules_from_project_markers(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n[tool.ruff]\n[tool.mypy]\n",
        encoding="utf-8",
    )
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text(
        '{"scripts":{"test":"vitest run","build":"vite build","dev":"vite"}}',
        encoding="utf-8",
    )
    management, _controller = _management(tmp_path)

    snapshot = management.snapshot()

    suggestions = snapshot.verification.suggestions
    assert [(item.command, item.cwd, item.scope) for item in suggestions] == [
        ("python -m pytest -q", ".", "full_project"),
        ("python -m ruff check .", ".", "full_project"),
        ("python -m mypy", ".", "full_project"),
        ("npm test", "web", "focused"),
        ("npm run build", "web", "focused"),
    ]
    assert suggestions[3].target_paths == ("web",)


def test_runtime_suggests_focused_python_rules_for_nested_projects(tmp_path: Path) -> None:
    exercise = tmp_path / "algorithm_practice"
    (exercise / "tests").mkdir(parents=True)
    (exercise / "tests" / "test_trap.py").write_text("def test_trap():\n    assert True\n")
    management, _controller = _management(tmp_path)

    suggestions = management.snapshot().verification.suggestions

    assert any(
        item.command == "python -m pytest -q"
        and item.cwd == "algorithm_practice"
        and item.target_paths == ("algorithm_practice",)
        and item.scope == "focused"
        for item in suggestions
    )


def test_runtime_lifecycle_is_explicit_and_sanitized(tmp_path: Path) -> None:
    management, _ = _management(tmp_path)

    management.set_lifecycle(LifecycleState.REQUESTING)

    assert management.snapshot().lifecycle is LifecycleState.REQUESTING


class _SkillDraftModel:
    def __init__(self, events: list[ModelStreamEvent]) -> None:
        self.events = events
        self.requests: list[tuple[list[dict[str, object]], list[dict[str, object]]]] = []

    def stream(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> Iterator[ModelStreamEvent]:
        self.requests.append((messages, tools))
        yield from self.events


def test_skill_draft_uses_the_current_model_without_exposing_tools(tmp_path: Path) -> None:
    management, controller = _management(tmp_path)
    controller.model = _SkillDraftModel(
        [
            ModelStreamEvent(
                type="text_delta",
                text=(
                    '{"name":"boundary-review","description":"Review boundary behavior.",'
                    '"instructions":"# Workflow\\n\\n1. Read the rules.\\n2. Review boundaries."}'
                ),
            ),
            ModelStreamEvent(type="done"),
        ]
    )

    draft = management.draft_skill(
        requirement="帮我检查改动是否越过工作区边界",
        template="review",
    )

    assert draft.name == "boundary-review"
    assert draft.generated_by == "model"
    assert draft.instructions.startswith("# Workflow")
    assert controller.model.requests[0][1] == []
    assert "帮我检查改动是否越过工作区边界" in str(controller.model.requests[0][0])


def test_skill_draft_falls_back_to_a_reviewable_local_template(tmp_path: Path) -> None:
    management, controller = _management(tmp_path)
    controller.model = _SkillDraftModel(
        [ModelStreamEvent(type="error", error="provider unavailable")]
    )

    draft = management.draft_skill(
        requirement="每次修改文档后检查链接和标题层级",
        template="documentation",
    )

    assert draft.generated_by == "template"
    assert draft.name == "documentation-helper"
    assert "每次修改文档后检查链接和标题层级" in draft.instructions


def test_skill_creation_requires_trust_for_repo_scope_and_refreshes_catalog(
    tmp_path: Path,
) -> None:
    management, controller = _management(tmp_path)
    controller.skills = SkillRegistry(workspace=tmp_path, user_root=tmp_path / "user-skills")
    controller.skills.discover(include_repo=True)

    created = management.create_skill(
        scope="repo",
        name="workspace-review",
        description="Review this workspace.",
        instructions="# Workflow\n\nRead AGENTS.md before reviewing.",
    )

    assert [item["name"] for item in created.items] == ["workspace-review"]
    assert (tmp_path / ".agents" / "skills" / "workspace-review" / "SKILL.md").is_file()

    management.runtime.trusted_project = False
    with pytest.raises(ValueError, match="trusted"):
        management.create_skill(
            scope="repo",
            name="untrusted-write",
            description="Must not be created.",
            instructions="Do not write this file.",
        )


def test_provider_upsert_writes_only_metadata_and_selects_for_next_runtime(tmp_path: Path) -> None:
    management, controller = _management(tmp_path)

    result = management.upsert_model_provider(
        provider="open-router",
        base_url="https://openrouter.ai/api/v1",
        model="vendor/model",
    )

    assert result.provider == "open-router"
    assert result.api_key_env == "FORGE_PROVIDER_OPEN_ROUTER_API_KEY"
    assert result.requires_restart is True
    assert management.runtime.model_state.load().provider == "open-router"
    catalog_text = management.runtime.catalog.path.read_text(encoding="utf-8")
    assert "vendor/model" in catalog_text
    assert "api_key =" not in catalog_text
    assert controller.sessions.list()[0]["model"] == "vendor/model"


def test_model_catalog_exposes_editable_metadata_without_credentials(tmp_path: Path) -> None:
    management, _ = _management(tmp_path)
    management.upsert_model_provider(
        provider="open-router",
        base_url="https://openrouter.ai/api/v1",
        model="vendor/model",
    )

    provider = management.model_catalog().providers[0]

    assert provider.name == "open-router"
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert provider.compatibility == "openai"
    assert "key" not in provider.model_dump_json().casefold()


def test_delete_model_provider_rejects_the_active_provider_and_removes_an_inactive_one(
    tmp_path: Path,
) -> None:
    management, controller = _management(tmp_path)
    management.upsert_model_provider(
        provider="open-router",
        base_url="https://openrouter.ai/api/v1",
        model="vendor/model",
    )
    management.upsert_model_provider(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )
    management.runtime.model_state.save(provider="open-router", model="vendor/model")
    controller.model_manager = SimpleNamespace(provider="open-router")

    with pytest.raises(ValueError, match="active provider"):
        management.delete_model_provider("open-router")

    catalog = management.delete_model_provider("deepseek")

    assert [provider.name for provider in catalog.providers] == ["open-router"]


def test_model_level_management_protects_only_the_active_model(tmp_path: Path) -> None:
    management, controller = _management(tmp_path)
    management.upsert_model_provider(
        provider="glm",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-5.3-flash",
    )
    management.upsert_model_provider(
        provider="glm",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-5.2-flash",
    )
    management.runtime.model_state.save(provider="glm", model="glm-5.3-flash")
    controller.model_manager = SimpleNamespace(provider="glm")
    controller.settings.model.name = "glm-5.3-flash"

    with pytest.raises(ValueError, match="active model"):
        management.delete_model("glm", "glm-5.3-flash")

    catalog = management.delete_model("glm", "glm-5.2-flash")
    assert catalog.providers[0].models == ("glm-5.3-flash",)


def test_update_model_preserves_the_current_selection_when_editing_an_inactive_model(
    tmp_path: Path,
) -> None:
    management, controller = _management(tmp_path)
    management.upsert_model_provider(
        provider="glm",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-current",
    )
    management.upsert_model_provider(
        provider="glm",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-other",
    )
    management.runtime.model_state.save(provider="glm", model="glm-current")
    controller.model_manager = SimpleNamespace(provider="glm")
    controller.settings.model.name = "glm-current"

    result = management.update_model(
        provider="glm",
        original_model="glm-other",
        model="glm-renamed",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        compatibility="openai",
    )

    assert result.active.id == "glm-current"
    assert result.providers[0].models == ("glm-renamed", "glm-current")
    assert management.runtime.model_state.load().model == "glm-current"


def test_probe_model_reports_success_and_sanitizes_provider_errors(tmp_path: Path) -> None:
    management, _ = _management(tmp_path)
    management.runtime.model = SimpleNamespace(
        stream=lambda _messages, _tools: iter(
            [SimpleNamespace(type="text_delta", text="OK"), SimpleNamespace(type="done")]
        )
    )

    assert management.probe_model().ok is True

    management.runtime.model = SimpleNamespace(
        stream=lambda _messages, _tools: iter(
            [SimpleNamespace(type="error", error="401 invalid api key sk-secret-value")]
        )
    )
    failed = management.probe_model()
    assert failed.ok is False
    assert failed.category == "authentication"
    assert "sk-secret-value" not in failed.message


def test_model_selection_records_the_active_model_in_the_current_session(tmp_path: Path) -> None:
    management, controller = _management(tmp_path)

    def switch(provider: str, model: str) -> SimpleNamespace:
        controller.model_manager.provider = provider
        controller.settings.model.name = model
        return SimpleNamespace(provider=provider, model=model)

    controller.model_manager = SimpleNamespace(
        provider="gemini",
        switch=switch,
    )
    management.runtime.catalog.path.write_text(
        """
default_provider = "open-router"

[providers.open-router]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
default_model = "vendor/fast-model"
models = ["vendor/fast-model"]
compatibility = "openai"
""".lstrip(),
        encoding="utf-8",
    )
    management.runtime.catalog.reload()

    management.select_model("open-router", "vendor/fast-model")

    assert controller.sessions.list()[0]["model"] == "vendor/fast-model"
    configuration = controller.sessions.replay(controller.session_id)[-1]
    assert configuration["type"] == "configuration"
    assert configuration["data"] == {
        "provider": "open-router",
        "model": "vendor/fast-model",
    }
