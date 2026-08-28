from __future__ import annotations

from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path

from prompt_toolkit.document import Document
from rich.console import Console

from coding_agent.config import Settings
from coding_agent.controller import AgentController
from coding_agent.events import AgentEvent, AgentState, EventKind
from coding_agent.memory import MemoryStore
from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.session import SessionStore
from coding_agent.skills import SkillRegistry
from coding_agent.tools.registry import default_registry
from coding_agent.ui.completion import AgentCompleter
from coding_agent.ui.prompt import InteractiveShell
from coding_agent.ui.render import JsonlRenderer, RichRenderer


def test_rich_renderer_narrow_terminal_and_no_color(tmp_path: Path) -> None:
    output = StringIO()
    console = Console(file=output, width=80, color_system=None, force_terminal=False)
    renderer = RichRenderer(console=console)
    renderer.header(model="fake", cwd="repo", permissions="prompt")
    renderer.handle(
        AgentEvent(
            kind=EventKind.PLAN,
            session_id="s",
            data={"plan": [{"step": "read files", "status": "in_progress"}]},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.TOOL_CALL,
            session_id="s",
            data={"name": "read_file", "arguments": {"path": "a.py"}},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.TOOL_RESULT,
            session_id="s",
            data={"result": {"ok": True, "summary": "read a.py", "data": {}}},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.COMPLETED,
            data={"reason": "done"},
        )
    )
    value = output.getvalue()
    assert "Forge Coding Agent" in value
    assert "coding-agent" in value and "read_file" in value and "completed" in value
    assert "\x1b[" not in value


def test_jsonl_renderer_and_completions(tmp_path: Path) -> None:
    output = StringIO()
    renderer = JsonlRenderer(Console(file=output, color_system=None))
    renderer.handle(AgentEvent(kind=EventKind.WARNING, session_id="s", data={"message": "x"}))
    assert '"kind":"warning"' in output.getvalue()

    skill_dir = tmp_path / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n", encoding="utf-8"
    )
    (tmp_path / "alpha.py").write_text("", encoding="utf-8")
    skills = SkillRegistry(workspace=tmp_path, user_root=tmp_path / "user")
    skills.discover(include_repo=True)
    completer = AgentCompleter(tmp_path, skills)
    slash = list(completer.get_completions(Document("/sta", 4), object()))
    skill = list(completer.get_completions(Document("$de", 3), object()))
    files = list(completer.get_completions(Document("@alp", 4), object()))
    assert any(item.text == "/status" for item in slash)
    assert any(item.text == "$demo" for item in skill)
    assert any(item.text == "@alpha.py" for item in files)


def test_streamed_assistant_text_is_rendered_as_markdown() -> None:
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None, width=80))
    renderer.handle(AgentEvent(kind=EventKind.TEXT, session_id="s", data={"delta": "**Result**"}))
    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.COMPLETED,
            data={"reason": "done"},
        )
    )
    value = output.getvalue()
    assert "Result" in value
    assert "**Result**" not in value


def test_markdown_wrap_keeps_end_of_long_line() -> None:
    output = StringIO()
    renderer = RichRenderer(
        console=Console(
            file=output,
            color_system=None,
            force_terminal=False,
            soft_wrap=False,
            width=40,
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.TEXT,
            session_id="s",
            data={"delta": "- " + "long content " * 10 + "END_MARKER"},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.COMPLETED,
            data={"reason": "done"},
        )
    )

    assert "END_MARKER" in output.getvalue()


def test_terminal_stream_uses_live_markdown_and_stops_cleanly() -> None:
    output = StringIO()
    console = Console(
        file=output,
        color_system="standard",
        force_terminal=True,
        width=80,
    )
    renderer = RichRenderer(console=console)
    renderer.handle(
        AgentEvent(kind=EventKind.TEXT, session_id="s", data={"delta": "**Live result**"})
    )
    assert renderer._live is not None

    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.COMPLETED,
            data={"reason": "done"},
        )
    )

    assert renderer._live is None
    assert "Live result" in output.getvalue()


def test_runtime_status_stays_live_during_tools_and_streaming() -> None:
    output = StringIO()
    console = Console(
        file=output,
        color_system="standard",
        force_terminal=True,
        width=120,
        height=24,
    )
    renderer = RichRenderer(console=console)
    provider_calls = 0

    def status() -> dict[str, object]:
        nonlocal provider_calls
        provider_calls += 1
        return {
            "model": "fake",
            "max_steps": 24,
            "plan_completed": 1,
            "plan_total": 3,
            "context_tokens": 128,
            "context_window": 32768,
        }

    renderer.start_turn_status(status)
    assert renderer._turn_live is not None
    assert provider_calls == 1

    renderer.handle(
        AgentEvent(
            kind=EventKind.STATE,
            session_id="s",
            state=AgentState.EXECUTING,
            data={"step": 2, "tool": "read_file"},
        )
    )
    renderer.handle(AgentEvent(kind=EventKind.TEXT, session_id="s", data={"delta": "**Done**"}))

    assert renderer._turn_live is not None
    assert renderer._live is None
    assert renderer._runtime_state is AgentState.EXECUTING
    assert provider_calls == 2
    renderer.handle(
        AgentEvent(
            kind=EventKind.APPROVAL,
            session_id="s",
            state=AgentState.AWAITING_APPROVAL,
            data={"request": {"summary": "approve read"}},
        )
    )
    assert renderer._runtime_state is AgentState.AWAITING_APPROVAL
    assert provider_calls == 3
    renderer.stop_turn_status()

    assert renderer._turn_live is None
    rendered = output.getvalue()
    assert "\x1b[24;1H" not in rendered
    assert "Running" in rendered
    assert "context left" in rendered
    assert "Forge Coding Agent" not in rendered
    assert "Done" in rendered


def test_plan_updates_only_render_changed_steps() -> None:
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None, width=80))
    renderer.handle(
        AgentEvent(
            kind=EventKind.PLAN,
            session_id="s",
            data={"plan": [{"step": "Read files", "status": "pending"}]},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.PLAN,
            session_id="s",
            data={"plan": [{"step": "Read files", "status": "completed"}]},
        )
    )

    rendered = output.getvalue()
    assert rendered.count("Plan") == 1
    assert rendered.count("Read files") == 2


def test_renderer_falls_back_to_ascii_for_gbk_output() -> None:
    binary = BytesIO()
    output = TextIOWrapper(binary, encoding="gbk")
    renderer = RichRenderer(
        console=Console(file=output, color_system=None, force_terminal=False, width=80)
    )

    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.FAILED,
            data={"reason": "connection error"},
        )
    )
    output.flush()

    rendered = binary.getvalue().decode("gbk")
    assert "x failed" in rendered
    assert "connection error" in rendered


def test_slash_commands_update_local_session_state(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class FakePromptSession:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            self.completer = kwargs.get("completer")

    class NoopModel:
        model = "fake"

        def stream(self, messages, tools):  # type: ignore[no-untyped-def]
            return iter(())

    monkeypatch.setattr("coding_agent.ui.prompt.PromptSession", FakePromptSession)
    settings = Settings(
        cwd=tmp_path,
        data_dir=tmp_path / "data",
        model={"name": "fake", "api_key": "test"},
    )
    memory = MemoryStore(data_dir=settings.data_dir, workspace=tmp_path, enabled=False)
    skills = SkillRegistry(workspace=tmp_path, user_root=tmp_path / "user")
    skills.discover(include_repo=False)
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None))
    controller = AgentController(
        settings=settings,
        model=NoopModel(),  # type: ignore[arg-type]
        tools=default_registry(),
        sessions=SessionStore(settings.data_dir),
        approval=ApprovalPolicy("prompt"),
        memory=memory,
        skills=skills,
    )
    shell = InteractiveShell(
        controller=controller,
        controller_factory=lambda _: controller,
        renderer=renderer,
        history_file=tmp_path / "history",
    )
    assert not shell._slash("/permissions read-only")
    assert controller.approval.mode == "read-only"
    shell._slash("/memory on")
    shell._slash("/memory remember Run pytest before commit")
    assert memory.enabled and memory.list()[0].content == "Run pytest before commit"
    shell._slash("/raw")
    assert renderer.raw
    assert shell._slash("/exit")
