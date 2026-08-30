from __future__ import annotations

from pathlib import Path

from coding_agent.events import AgentEvent
from coding_agent.runtime import RuntimeFactory
from coding_agent.safety.approval import ApprovalDecision, ApprovalRequest
from coding_agent.workspace_settings import WorkspaceSettingsStore


def _write_model_catalog(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "models.toml").write_text(
        """
default_provider = "gemini"

[providers.gemini]
base_url = "https://gemini.example/v1"
api_key_env = "GEMINI_API_KEY"
default_model = "gemini-flash"
models = ["gemini-flash", "gemini-pro"]
compatibility = "gemini"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_runtime_factory_preserves_model_and_workspace_configuration(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_model_catalog(data_dir)
    WorkspaceSettingsStore(data_dir=data_dir, workspace=tmp_path).set_max_steps(48)

    runtime = RuntimeFactory(
        workspace=tmp_path,
        data_dir=data_dir,
        permissions="read-only",
        trusted_project=False,
        interactive=False,
        model_name="gemini-pro",
        environ={"GEMINI_API_KEY": "secret-value"},
    )
    controller = runtime.create()

    assert runtime.settings.agent.configured_max_steps == 24
    assert runtime.settings.agent.max_steps == 48
    assert controller.settings.model.name == "gemini-pro"
    assert controller.settings.model.base_url == "https://gemini.example/v1"
    assert controller.model.compatibility == "gemini"
    assert controller.model_manager is not None
    assert controller.model_manager.provider == "gemini"


def test_runtime_factory_keeps_frontend_callbacks_and_session_approval_isolated(
    tmp_path: Path,
) -> None:
    events: list[AgentEvent] = []
    approvals: list[str] = []
    event_sink = events.append

    def approve(request: ApprovalRequest) -> ApprovalDecision:
        approvals.append(request.subject)
        return ApprovalDecision.ALLOW_SESSION

    runtime = RuntimeFactory(
        workspace=tmp_path,
        data_dir=tmp_path / "data",
        permissions="prompt",
        trusted_project=False,
        interactive=True,
        event_sink=event_sink,
        approval_callback=approve,
        environ={"OPENAI_API_KEY": "secret-value"},
    )
    first = runtime.create()
    second = runtime.controller_factory()(None)
    request = ApprovalRequest(action="write_file", subject="a.txt", summary="write a file")

    assert first.event_sink is event_sink
    assert first.approval is not second.approval
    assert first.approval.decide(request) is ApprovalDecision.ALLOW_SESSION
    assert first.approval.session_grant_count == 1
    assert second.approval.session_grant_count == 0
    assert approvals == ["a.txt"]


def test_runtime_factory_loads_project_resources_only_when_trusted(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Project-only instruction.\n", encoding="utf-8")
    environ = {"OPENAI_API_KEY": "secret-value"}

    untrusted = RuntimeFactory(
        workspace=tmp_path,
        data_dir=tmp_path / "untrusted-data",
        permissions="read-only",
        trusted_project=False,
        interactive=False,
        environ=environ,
    ).create()
    trusted = RuntimeFactory(
        workspace=tmp_path,
        data_dir=tmp_path / "trusted-data",
        permissions="read-only",
        trusted_project=True,
        interactive=False,
        environ=environ,
    ).create()

    assert untrusted.agents_instructions == ""
    assert "Project-only instruction." in trusted.agents_instructions
