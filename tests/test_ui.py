from __future__ import annotations

from io import BytesIO, StringIO, TextIOWrapper
from itertools import pairwise
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import set_app
from prompt_toolkit.buffer import CompletionState
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.utils import get_cwidth
from rich.console import Console

import coding_agent.ui.prompt as prompt_module
from coding_agent.config import Settings
from coding_agent.controller import AgentController
from coding_agent.events import AgentEvent, AgentState, EventKind
from coding_agent.memory import MemoryStore
from coding_agent.model_catalog import ModelCatalog
from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.session import SessionStore
from coding_agent.skills import SkillRegistry
from coding_agent.tools.registry import default_registry
from coding_agent.ui.cancel import EscapeMonitor
from coding_agent.ui.completion import AgentCompleter
from coding_agent.ui.prompt import (
    InteractiveShell,
    _continuation,
    _prompt_style,
    _PromptBackgroundProcessor,
)
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
    status_completion = next(item for item in slash if item.text == "/status")
    assert "会话" in str(status_completion.display_meta)
    assert any(item.text == "$demo" for item in skill)
    assert any(item.text == "@alpha.py" for item in files)


def test_model_and_steps_argument_completion(tmp_path: Path) -> None:
    skills = SkillRegistry(workspace=tmp_path, user_root=tmp_path / "user")
    skills.discover(include_repo=False)
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text(
        """
default_provider = "gemini"
[providers.gemini]
api_key_env = "GEMINI_API_KEY"
default_model = "gemini-flash"
models = ["gemini-flash", "gemini-pro"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    completer = AgentCompleter(
        tmp_path,
        skills,
        model_catalog=ModelCatalog(path=catalog_path, environ={}),
    )

    providers = list(completer.get_completions(Document("/model use ge"), object()))
    models = list(completer.get_completions(Document("/model use gemini gemini-p"), object()))
    steps = list(completer.get_completions(Document("/steps r"), object()))

    assert [item.text for item in providers] == ["gemini"]
    assert [item.text for item in models] == ["gemini-pro"]
    assert [item.text for item in steps] == ["reset"]


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


def test_user_input_background_is_applied_before_submission() -> None:
    transformation = _PromptBackgroundProcessor().apply_transformation(
        SimpleNamespace(fragments=[("", "inspect the repository")])  # type: ignore[arg-type]
    )

    style, content = transformation.fragments[0]
    assert content == "inspect the repository"
    assert style == "class:composer-text"


def test_idle_composer_is_content_height_plus_vertical_padding(
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    class NoopModel:
        model = "fake"

        def stream(self, messages, tools):  # type: ignore[no-untyped-def]
            return iter(())

    settings = Settings(
        cwd=tmp_path,
        data_dir=tmp_path / "data",
        model={"name": "fake", "api_key": "test"},
    )
    skills = SkillRegistry(workspace=tmp_path, user_root=tmp_path / "user")
    skills.discover(include_repo=False)
    real_prompt_session = PromptSession

    def prompt_session(**kwargs):  # type: ignore[no-untyped-def]
        return real_prompt_session(input=DummyInput(), output=DummyOutput(), **kwargs)

    monkeypatch.setattr(prompt_module, "PromptSession", prompt_session)
    controller = AgentController(
        settings=settings,
        model=NoopModel(),  # type: ignore[arg-type]
        tools=default_registry(),
        sessions=SessionStore(settings.data_dir),
        approval=ApprovalPolicy("prompt"),
        skills=skills,
    )
    shell = InteractiveShell(
        controller=controller,
        controller_factory=lambda _: controller,
        renderer=RichRenderer(console=Console(file=StringIO(), color_system=None)),
        history_file=tmp_path / "history",
    )

    assert shell.composer is not None
    shell.session.default_buffer._load_history_task = object()
    with set_app(shell.session.app):
        dimension = shell.composer.preferred_height(100, 24)

    assert (dimension.min, dimension.preferred, dimension.max) == (3, 3, 3)


def test_completion_menu_expands_outside_compact_composer(
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    class NoopModel:
        model = "fake"

        def stream(self, messages, tools):  # type: ignore[no-untyped-def]
            return iter(())

    settings = Settings(
        cwd=tmp_path,
        data_dir=tmp_path / "data",
        model={"name": "fake", "api_key": "test"},
    )
    skills = SkillRegistry(workspace=tmp_path, user_root=tmp_path / "user")
    skills.discover(include_repo=False)
    real_prompt_session = PromptSession

    def prompt_session(**kwargs):  # type: ignore[no-untyped-def]
        return real_prompt_session(input=DummyInput(), output=DummyOutput(), **kwargs)

    monkeypatch.setattr(prompt_module, "PromptSession", prompt_session)
    controller = AgentController(
        settings=settings,
        model=NoopModel(),  # type: ignore[arg-type]
        tools=default_registry(),
        sessions=SessionStore(settings.data_dir),
        approval=ApprovalPolicy("prompt"),
        skills=skills,
    )
    shell = InteractiveShell(
        controller=controller,
        controller_factory=lambda _: controller,
        renderer=RichRenderer(console=Console(file=StringIO(), color_system=None)),
        history_file=tmp_path / "history",
    )
    assert shell.composer is not None
    shell.session.default_buffer._load_history_task = object()
    shell.session.default_buffer.complete_state = CompletionState(
        original_document=Document("/"),
        completions=[Completion("/help"), Completion("/status")],
    )

    with set_app(shell.session.app):
        composer_height = shell.composer.preferred_height(100, 24).preferred
        layout_height = shell.session.layout.container.preferred_height(100, 24).preferred

    assert composer_height == 3
    assert layout_height > composer_height
    assert shell.completion_window is not None
    assert not shell.completion_window.dont_extend_width()
    with set_app(shell.session.app):
        assert shell.completion_window.preferred_height(100, 24).preferred == 2


def test_no_color_removes_processor_and_prompt_toolkit_default_colors(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    transformation = _PromptBackgroundProcessor().apply_transformation(
        SimpleNamespace(fragments=[("", "task")])  # type: ignore[arg-type]
    )
    session: PromptSession[str] = PromptSession(
        input=DummyInput(), output=DummyOutput(), style=_prompt_style()
    )

    assert transformation.fragments[0][0] == "class:composer-text"
    toolbar = session.app._merged_style.get_attrs_for_style_str("class:bottom-toolbar")
    completion_meta = session.app._merged_style.get_attrs_for_style_str(
        "class:completion-menu.meta.completion"
    )
    assert not toolbar.reverse and toolbar.bgcolor == "default"
    assert completion_meta.color == "default" and completion_meta.bgcolor == "default"


def test_completion_menu_uses_one_background_across_command_and_description(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    session: PromptSession[str] = PromptSession(
        input=DummyInput(), output=DummyOutput(), style=_prompt_style()
    )

    completion = session.app._merged_style.get_attrs_for_style_str(
        "class:completion-menu.completion"
    )
    meta = session.app._merged_style.get_attrs_for_style_str(
        "class:completion-menu.meta.completion"
    )
    current = session.app._merged_style.get_attrs_for_style_str(
        "class:completion-menu.completion.current"
    )
    current_meta = session.app._merged_style.get_attrs_for_style_str(
        "class:completion-menu.meta.completion.current"
    )

    assert meta.bgcolor == completion.bgcolor
    assert current_meta.bgcolor == current.bgcolor


def test_wrapped_input_continuation_aligns_without_a_marker() -> None:
    assert _continuation(2, 1, 80) == [("class:continuation", "  ")]


def test_turn_sections_use_one_rule_for_direct_output_and_two_after_activity() -> None:
    def render(*events: AgentEvent) -> list[str]:
        output = StringIO()
        renderer = RichRenderer(console=Console(file=output, color_system=None, width=80))
        renderer.start_turn_status(
            lambda: {
                "max_steps": 24,
                "context_tokens": 0,
                "context_window": 32768,
            }
        )
        for event in events:
            renderer.handle(event)
        renderer.stop_turn_status()
        return [line.strip() for line in output.getvalue().splitlines()]

    text = AgentEvent(kind=EventKind.TEXT, session_id="s", data={"delta": "answer"})
    done = AgentEvent(
        kind=EventKind.DONE,
        session_id="s",
        state=AgentState.COMPLETED,
        data={"reason": "done"},
    )
    tool = AgentEvent(
        kind=EventKind.TOOL_CALL,
        session_id="s",
        data={"name": "read_file", "arguments": {"path": "README.md"}},
    )
    result = AgentEvent(
        kind=EventKind.TOOL_RESULT,
        session_id="s",
        data={"result": {"ok": True, "summary": "read README.md"}},
    )

    direct = render(text, done)
    with_activity = render(tool, result, text, done)
    expected_rule = "─" * 78
    assert direct.count(expected_rule) == 1
    assert with_activity.count(expected_rule) == 2
    for lines in (direct, with_activity):
        for index, line in enumerate(lines):
            if line == expected_rule:
                assert index + 1 < len(lines)
                assert lines[index + 1] != ""
                if index:
                    assert lines[index - 1] != ""


def test_completed_turn_uses_full_width_rule_before_next_prompt() -> None:
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None, width=80))
    renderer.start_turn_status(
        lambda: {"max_steps": 24, "context_tokens": 0, "context_window": 32768}
    )
    renderer.handle(AgentEvent(kind=EventKind.TEXT, session_id="s", data={"delta": "answer"}))
    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.COMPLETED,
            data={"reason": "done"},
        )
    )
    renderer.stop_turn_status()

    renderer.prompt_boundary()

    lines = [line.strip() for line in output.getvalue().splitlines()]
    completed = next(index for index, line in enumerate(lines) if "completed" in line)
    assert lines[completed + 1] == "─" * 78


def test_header_uses_same_width_as_wide_terminal() -> None:
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None, width=140))

    renderer.header(model="fake", cwd="repo", permissions="prompt")

    assert max(len(line) for line in output.getvalue().splitlines()) == 140


def test_all_agent_output_uses_the_same_response_indent() -> None:
    output = StringIO()
    renderer = RichRenderer(console=Console(file=output, color_system=None, width=80))
    renderer.handle(
        AgentEvent(
            kind=EventKind.TOOL_CALL,
            session_id="s",
            data={"name": "read_file", "arguments": {"path": "README.md"}},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.TOOL_RESULT,
            session_id="s",
            data={"result": {"ok": True, "summary": "read README.md"}},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.PLAN,
            session_id="s",
            data={"plan": [{"step": "Inspect files", "status": "in_progress"}]},
        )
    )
    renderer.handle(
        AgentEvent(
            kind=EventKind.APPROVAL,
            session_id="s",
            data={"request": {"summary": "edit README.md", "action": "edit_file"}},
        )
    )
    renderer.handle(AgentEvent(kind=EventKind.TEXT, session_id="s", data={"delta": "Result"}))
    renderer.handle(
        AgentEvent(
            kind=EventKind.DONE,
            session_id="s",
            state=AgentState.COMPLETED,
            data={"reason": "done"},
        )
    )

    lines = output.getvalue().splitlines()
    call_index = next(index for index, line in enumerate(lines) if "read_file" in line)
    result_index = next(index for index, line in enumerate(lines) if "read README.md" in line)
    assert lines[call_index].startswith("  ")
    assert result_index == call_index + 1
    for marker in ("Plan", "Approval required", "completed"):
        index = next(index for index, line in enumerate(lines) if marker in line)
        assert lines[index].startswith("  ")
        assert lines[index - 1] == ""
    response_index = next(index for index, line in enumerate(lines) if "Result" in line)
    assert lines[response_index].startswith("  ")
    assert lines[response_index - 1].strip() == "─" * 78
    assert not any(left == right == "" for left, right in pairwise(lines))


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
    assert not renderer.accepts_escape_cancel
    assert provider_calls == 3
    assert renderer.pause_turn_status()
    assert renderer._turn_live is None
    renderer.resume_turn_status()
    assert renderer._turn_live is not None
    renderer.stop_turn_status()

    assert renderer._turn_live is None
    rendered = output.getvalue()
    assert "\x1b[24;1H" not in rendered
    assert "Running" in rendered
    assert "context left" in rendered
    assert "Forge Coding Agent" not in rendered
    assert "Done" in rendered


def test_runtime_status_uses_available_columns_instead_of_fixed_breakpoint() -> None:
    renderer = RichRenderer(
        console=Console(file=StringIO(), color_system=None, force_terminal=False, width=79)
    )
    renderer.start_turn_status(
        lambda: {
            "max_steps": 8,
            "context_tokens": 128,
            "context_window": 32768,
        }
    )

    status = renderer._runtime_status_text().plain

    assert "context left" in status
    assert get_cwidth(status) <= 76


def test_runtime_status_keeps_one_blank_line_above_live_footer() -> None:
    output = StringIO()
    renderer = RichRenderer(
        console=Console(file=output, color_system=None, force_terminal=False, width=80)
    )
    renderer.start_turn_status(
        lambda: {"max_steps": 8, "context_tokens": 0, "context_window": 32768}
    )

    renderer.console.print(renderer._turn_renderable())

    lines = output.getvalue().splitlines()
    assert lines[0].strip() == ""
    assert "Working" in lines[1]


def test_renderer_reflows_new_output_when_visible_width_changes() -> None:
    output = StringIO()
    visible_width = 48
    renderer = RichRenderer(
        console=Console(file=output, color_system=None, force_terminal=False, width=160)
    )
    renderer.set_viewport_width_provider(lambda: visible_width)

    renderer.markdown("word " * 30)
    first_render = output.getvalue().splitlines()
    assert max(get_cwidth(line) for line in first_render) <= 48

    visible_width = 32
    renderer.prompt_boundary()

    assert renderer.console.width == 32
    assert output.getvalue().splitlines()[-1].strip() == "─" * 30


def test_live_status_rechecks_visible_width_during_refresh() -> None:
    visible_width = 80
    renderer = RichRenderer(
        console=Console(file=StringIO(), color_system="standard", force_terminal=True, width=160)
    )
    renderer.set_viewport_width_provider(lambda: visible_width)
    renderer.start_turn_status(
        lambda: {"max_steps": 8, "context_tokens": 0, "context_window": 32768}
    )
    assert renderer._turn_live is not None

    visible_width = 45
    renderer._turn_live.get_renderable()

    assert renderer.console.width == 45
    renderer.stop_turn_status()


def test_diff_rendering_and_escape_monitor() -> None:
    diff = "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-old\n+new\n context\n"
    rendered = RichRenderer.diff_text(diff)
    assert rendered.plain == diff
    styles = {str(span.style) for span in rendered.spans}
    assert any("#173522" in style for style in styles)
    assert any("#3a1c22" in style for style in styles)

    event = Event()
    monitor = EscapeMonitor(event, enabled=lambda: False)
    assert not monitor.feed("\x1b") and not event.is_set()
    monitor = EscapeMonitor(event)
    assert not monitor.feed("x") and not event.is_set()
    assert monitor.feed("\x1b") and event.is_set()


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
    shell._slash("/raw on")
    assert renderer.raw
    assert shell._slash("/exit")
