from __future__ import annotations

from io import StringIO
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
