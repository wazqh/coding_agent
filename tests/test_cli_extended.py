from __future__ import annotations

from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console
from typer.testing import CliRunner

import coding_agent.cli as cli
from coding_agent.config import ConfigError
from coding_agent.events import AgentState
from coding_agent.safety.approval import ApprovalDecision, ApprovalRequest
from coding_agent.ui.render import JsonlRenderer, RichRenderer


def test_data_directory_override_and_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "override"
    monkeypatch.setenv("CODING_AGENT_DATA_DIR", str(override))
    assert cli._data_dir() == override.resolve()
    monkeypatch.delenv("CODING_AGENT_DATA_DIR")
    monkeypatch.setattr(cli, "user_data_path", lambda *args, **kwargs: tmp_path / "default")
    assert cli._data_dir() == tmp_path / "default"


def test_project_trust_choices(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert not cli._resolve_trust(
        empty,
        tmp_path / "empty-data",
        interactive=True,
        trust_project=False,
        console=Console(file=StringIO(), color_system=None),
    )

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("Follow tests.\n", encoding="utf-8")
    console = Console(file=StringIO(), color_system=None)
    assert not cli._resolve_trust(
        workspace,
        tmp_path / "data",
        interactive=False,
        trust_project=False,
        console=console,
    )
    assert cli._resolve_trust(
        workspace,
        tmp_path / "data",
        interactive=False,
        trust_project=True,
        console=console,
    )
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "once")
    assert cli._resolve_trust(
        workspace,
        tmp_path / "data",
        interactive=True,
        trust_project=False,
        console=console,
    )
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "always")
    assert cli._resolve_trust(
        workspace,
        tmp_path / "trusted-data",
        interactive=True,
        trust_project=False,
        console=console,
    )
    assert cli._resolve_trust(
        workspace,
        tmp_path / "trusted-data",
        interactive=False,
        trust_project=False,
        console=console,
    )


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("1", ApprovalDecision.ALLOW_ONCE),
        ("2", ApprovalDecision.ALLOW_SESSION),
        ("3", ApprovalDecision.DENY),
        ("once", ApprovalDecision.ALLOW_ONCE),
        ("session", ApprovalDecision.ALLOW_SESSION),
        ("deny", ApprovalDecision.DENY),
    ],
)
def test_approval_prompt_mapping(
    choice: str,
    expected: ApprovalDecision,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: choice)
    callback = cli._approval_callback(Console(file=StringIO(), color_system=None))
    request = ApprovalRequest(action="write", subject="a.txt", summary="write file")
    assert callback(request) is expected


def test_approval_prompt_pauses_live_status(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Renderer:
        def pause_turn_status(self) -> bool:
            calls.append("pause")
            return True

        def resume_turn_status(self) -> None:
            calls.append("resume")

    output = StringIO()
    monkeypatch.setattr(cli.Prompt, "ask", lambda *args, **kwargs: "1")
    callback = cli._approval_callback(
        Console(file=output, color_system=None),
        Renderer(),  # type: ignore[arg-type]
    )
    request = ApprovalRequest(action="edit_file", subject="a.py", summary="edit a.py")
    assert callback(request) is ApprovalDecision.ALLOW_ONCE
    assert calls == ["pause", "resume"]
    assert "Choose an approval" in output.getvalue()


def test_build_runtime_variants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODING_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    controller, renderer, factory = cli._build_runtime(
        cwd=tmp_path,
        model_name="test-model",
        permissions="auto",
        interactive=False,
        output="jsonl",
        trust_project=False,
    )
    assert controller.settings.model.name == "test-model"
    assert isinstance(renderer, JsonlRenderer)
    replacement = factory(None)
    assert replacement.session_id != controller.session_id
    assert replacement.approval is not controller.approval
    assert replacement.memory is not controller.memory
    assert replacement.skills is not controller.skills

    _, rich, _ = cli._build_runtime(
        cwd=tmp_path,
        model_name=None,
        permissions="prompt",
        interactive=True,
        output="rich",
        trust_project=False,
    )
    assert isinstance(rich, RichRenderer)
    with pytest.raises(ConfigError, match="--output"):
        cli._build_runtime(
            cwd=tmp_path,
            model_name=None,
            permissions="auto",
            interactive=False,
            output="xml",
            trust_project=False,
        )
    with pytest.raises(ConfigError, match="--permissions"):
        cli._build_runtime(
            cwd=tmp_path,
            model_name=None,
            permissions="unsafe",
            interactive=False,
            output="rich",
            trust_project=False,
        )


def _fake_runtime(tmp_path: Path, *, exit_code: int = 0):
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None))
    settings = SimpleNamespace(
        model=SimpleNamespace(name="fake-model"),
        cwd=tmp_path,
        data_dir=tmp_path / "data",
    )
    result = SimpleNamespace(exit_code=exit_code, status=AgentState.COMPLETED)
    controller = SimpleNamespace(settings=settings, run_turn=lambda _task: result)
    return controller, renderer, lambda _session_id: controller


def test_cli_run_root_and_resume_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _fake_runtime(tmp_path)
    monkeypatch.setattr(cli, "_build_runtime", lambda **kwargs: runtime)

    class FakeShell:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def run(self) -> int:
            return 0

    monkeypatch.setattr(cli, "InteractiveShell", FakeShell)
    runner = CliRunner()
    assert runner.invoke(cli.app, []).exit_code == 0
    assert runner.invoke(cli.app, ["run", "inspect", "--cwd", str(tmp_path)]).exit_code == 0
    assert runner.invoke(cli.app, ["resume", "session", "--cwd", str(tmp_path)]).exit_code == 0


@pytest.mark.parametrize("command", [[], ["run", "inspect"], ["resume", "missing"]])
def test_cli_routes_report_configuration_errors(
    command: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**kwargs):
        raise ConfigError("bad configuration")

    monkeypatch.setattr(cli, "_build_runtime", fail)
    result = CliRunner().invoke(cli.app, command)
    assert result.exit_code == 2
    assert "bad configuration" in result.stderr


def test_sessions_table_contains_saved_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CODING_AGENT_DATA_DIR", str(data_dir))
    session_id = cli.SessionStore(data_dir).create({"workspace": str(tmp_path)})
    cli.SessionStore(data_dir).append_message(
        session_id, {"role": "user", "content": "inspect project"}
    )
    result = CliRunner().invoke(cli.app, ["sessions"])
    assert result.exit_code == 0
    assert session_id[:12] in result.stdout
    assert "inspect project" in result.stdout
