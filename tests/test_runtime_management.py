from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from coding_agent.model_catalog import ModelCatalog, ModelSelectionStore
from coding_agent.runtime_management import LifecycleState, RuntimeManagement
from coding_agent.safety.approval import ApprovalPolicy, ApprovalRequest
from coding_agent.session import SessionStore
from coding_agent.workspace_settings import WorkspaceSettingsStore


def _management(tmp_path: Path) -> tuple[RuntimeManagement, SimpleNamespace]:
    data_dir = tmp_path / ".data"
    settings = SimpleNamespace(
        cwd=tmp_path,
        agent=SimpleNamespace(
            max_steps=24,
            configured_max_steps=24,
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
    assert snapshot.steps.minimum == 12
    assert snapshot.steps.maximum == 100
    assert snapshot.steps.current == 24
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

    assert reset.steps.current == 24
    assert reset.steps.overridden is False
    assert management.workspace_settings.load().max_steps is None


def test_verification_commands_are_project_scoped_and_update_the_active_controller(
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
    assert management.workspace_settings.load().verification.commands == list(
        changed.verification.commands
    )

    reset = management.reset_verification_commands()

    assert reset.verification.commands == ()
    assert controller.verification_commands == ()


def test_runtime_lifecycle_is_explicit_and_sanitized(tmp_path: Path) -> None:
    management, _ = _management(tmp_path)

    management.set_lifecycle(LifecycleState.REQUESTING)

    assert management.snapshot().lifecycle is LifecycleState.REQUESTING


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
