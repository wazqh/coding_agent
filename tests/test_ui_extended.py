from __future__ import annotations

from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from prompt_toolkit.keys import Keys
from rich.console import Console

import coding_agent.ui.prompt as prompt_module
from coding_agent.config import Settings
from coding_agent.controller import AgentController
from coding_agent.events import AgentEvent, AgentState, EventKind, ModelStreamEvent
from coding_agent.memory import MemoryStore
from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.session import SessionError, SessionStore
from coding_agent.skills import SkillRegistry
from coding_agent.tools.registry import default_registry
from coding_agent.ui.prompt import InteractiveShell, _bindings
from coding_agent.ui.render import RichRenderer


class TextModel:
    model = "fake-model"

    def stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> Iterator[ModelStreamEvent]:
        yield ModelStreamEvent(type="text_delta", text="done")
        yield ModelStreamEvent(type="done", finish_reason="stop")


class FakePromptSession:
    def __init__(self, **kwargs: Any) -> None:
        self.completer = kwargs.get("completer")


def make_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[InteractiveShell, AgentController, StringIO]:
    monkeypatch.setattr(prompt_module, "PromptSession", FakePromptSession)
    skill_dir = tmp_path / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo workflow\n---\nUse the demo.\n",
        encoding="utf-8",
    )
    settings = Settings(
        cwd=tmp_path,
        data_dir=tmp_path / "data",
        model={"name": "fake-model", "api_key": "test"},
    )
    skills = SkillRegistry(workspace=tmp_path, user_root=tmp_path / "user")
    skills.discover(include_repo=True)
    controller = AgentController(
        settings=settings,
        model=TextModel(),  # type: ignore[arg-type]
        tools=default_registry(),
        sessions=SessionStore(settings.data_dir),
        approval=ApprovalPolicy("prompt"),
        memory=MemoryStore(data_dir=settings.data_dir, workspace=tmp_path),
        skills=skills,
    )
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None, width=80))

    def factory(session_id: str | None) -> AgentController:
        if session_id == "bad":
            raise SessionError("missing session")
        return controller

    shell = InteractiveShell(
        controller=controller,
        controller_factory=factory,
        renderer=renderer,
        history_file=tmp_path / "history",
    )
    toolbar = "".join(fragment for _, fragment in shell._bottom_toolbar())
    assert "fake-model" in toolbar
    assert "context left" in toolbar
    assert tmp_path.name in toolbar
    assert "Forge Coding Agent" not in toolbar
    return shell, controller, output


def test_interactive_shell_requires_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt_module, "PromptSession", FakePromptSession)
    controller = SimpleNamespace(skills=None)
    renderer = RichRenderer(console=Console(file=StringIO(), color_system=None))
    with pytest.raises(ValueError, match="skill registry"):
        InteractiveShell(
            controller=controller,  # type: ignore[arg-type]
            controller_factory=lambda _value: controller,  # type: ignore[arg-type,return-value]
            renderer=renderer,
            history_file=tmp_path / "history",
        )


def test_key_bindings_dispatch_to_buffer() -> None:
    calls: list[str] = []

    class Buffer:
        def insert_text(self, value: str) -> None:
            calls.append("insert:" + value)

        def validate_and_handle(self) -> None:
            calls.append("accept")

        def open_in_editor(self) -> None:
            calls.append("editor")

    event = SimpleNamespace(
        current_buffer=Buffer(),
        app=SimpleNamespace(renderer=SimpleNamespace(clear=lambda: calls.append("clear"))),
    )
    bindings = _bindings()
    for keys in (
        (Keys.ControlJ,),
        (Keys.ControlM,),
        (Keys.ControlG,),
        (Keys.ControlL,),
    ):
        bindings.get_bindings_for_keys(keys)[-1].handler(event)
    assert calls == ["insert:\n", "accept", "editor", "clear"]


def test_shell_run_handles_cancel_empty_command_and_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, controller, output = make_shell(tmp_path, monkeypatch)
    values: Iterator[str | BaseException] = iter(
        [KeyboardInterrupt(), "   ", "/help", "inspect", EOFError()]
    )

    class SequenceSession:
        completer = shell.session.completer

        def prompt(self, _prompt: str) -> str:
            value = next(values)
            if isinstance(value, BaseException):
                raise value
            return value

    shell.session = SequenceSession()  # type: ignore[assignment]
    assert shell.run() == 0
    text = output.getvalue()
    assert "已取消输入" in text
    assert "/status" in text
    assert "session saved" in text
    assert f"python -m coding_agent resume {controller.session_id}" in text
    assert any(message.get("content") == "inspect" for message in controller.conversation)


def test_shell_wraps_each_task_with_runtime_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, _, _ = make_shell(tmp_path, monkeypatch)
    calls: list[str] = []
    original_start = shell.renderer.start_turn_status
    original_stop = shell.renderer.stop_turn_status

    def start(provider):  # type: ignore[no-untyped-def]
        calls.append("start")
        original_start(provider)

    def stop() -> None:
        calls.append("stop")
        original_stop()

    monkeypatch.setattr(shell.renderer, "start_turn_status", start)
    monkeypatch.setattr(shell.renderer, "stop_turn_status", stop)
    values: Iterator[str | BaseException] = iter(["inspect", EOFError()])

    class SequenceSession:
        completer = shell.session.completer

        def prompt(self, _prompt: str) -> str:
            value = next(values)
            if isinstance(value, BaseException):
                raise value
            return value

    shell.session = SequenceSession()  # type: ignore[assignment]
    assert shell.run() == 0
    assert calls == ["start", "stop"]


def test_exit_command_prints_session_resume_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, controller, output = make_shell(tmp_path, monkeypatch)

    class ExitSession:
        completer = shell.session.completer

        def prompt(self, _prompt: str) -> str:
            return "/exit"

    shell.session = ExitSession()  # type: ignore[assignment]
    assert shell.run() == 0
    rendered = output.getvalue()
    assert f"session saved: {controller.session_id}" in rendered
    assert f"python -m coding_agent resume {controller.session_id}" in rendered


def test_slash_commands_cover_state_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell, controller, output = make_shell(tmp_path, monkeypatch)
    controller.working.plan = [{"step": "test", "status": "pending"}]
    assert not shell._slash("/help")
    assert not shell._slash("/status")
    assert not shell._slash("/model changed-model")
    assert controller.model.model == "changed-model"
    assert not shell._slash("/model")
    assert not shell._slash("/permissions unsafe")
    assert not shell._slash("/permissions")
    assert not shell._slash("/plan")
    assert not shell._slash("/diff")
    controller.working.diffs.append("--- a\n+++ b")
    assert not shell._slash("/diff")
    assert not shell._slash("/compact")
    assert not shell._slash("/clear")
    assert not shell._slash("/new")
    assert not shell._slash("/resume")
    assert not shell._slash("/resume bad")
    assert not shell._slash("/resume anything")
    assert not shell._slash("/unknown")
    assert "unknown command" in output.getvalue()


def test_memory_and_skill_slash_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shell, controller, output = make_shell(tmp_path, monkeypatch)
    memory = controller.memory
    assert memory is not None
    shell._slash("/memory list")
    shell._slash("/memory on")
    shell._slash("/memory remember Run pytest before commit")
    record_id = memory.list()[0].id
    shell._slash("/memory list")
    shell._slash("/memory forget missing")
    shell._slash(f"/memory forget {record_id}")
    shell._slash("/memory remember")
    shell._slash("/memory unknown")
    shell._slash("/memory clear")
    controller.memory = None
    shell._slash("/memory list")

    shell._slash("/skills")
    shell._slash("/skills search demo")
    shell._slash("/skills disable demo")
    shell._slash("/skills enable demo")
    shell._slash("/skills enable missing")
    shell._slash("/skills reload")
    assert controller.skills is not None
    controller.skills.diagnostics.append("bad skill")
    shell._slash("/skills")
    controller.skills = None
    shell._slash("/skills")
    text = output.getvalue()
    assert "remembered" in text
    assert "memory content is empty" in text
    assert "bad skill" in text


def test_rich_renderer_all_event_variants() -> None:
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None, width=60), raw=True)
    renderer.handle(AgentEvent(kind=EventKind.TEXT, session_id="s", data={"delta": "hello"}))
    renderer.handle(
        AgentEvent(
            kind=EventKind.TOOL_CALL,
            session_id="s",
            data={"name": "run_command", "arguments": {"command": "git status"}},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.TOOL_RESULT,
            session_id="s",
            data={"result": {"ok": False, "summary": "failed", "data": {"code": 1}}},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.APPROVAL,
            session_id="s",
            data={"request": {"summary": "edit", "diff": "--- a\n+++ b"}},
        )
    )
    renderer.handle(AgentEvent(kind=EventKind.ERROR, session_id="s", data={"message": "broken"}))
    renderer.handle(AgentEvent(kind=EventKind.WARNING, session_id="s", data={"message": "careful"}))
    renderer.handle(AgentEvent(kind=EventKind.COMPACT, session_id="s", data={"tokens_before": 100}))
    renderer.handle(AgentEvent(kind=EventKind.SKILL, session_id="s", data={"name": "demo"}))
    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.FAILED,
            data={"reason": "stopped"},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.CANCELLED,
            data={"reason": "cancelled"},
        )
    )
    renderer.render_plan([{"step": "unknown", "status": "other"}])
    renderer.markdown("# Result")
    renderer.status_table([("model", "fake")])
    assert RichRenderer._subject("not a mapping") == ""
    assert RichRenderer._subject({"pattern": "needle"}) == "  needle"
    text = output.getvalue()
    assert all(
        word in text for word in ("hello", "failed", "cancelled", "broken", "careful", "demo")
    )
