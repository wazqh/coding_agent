from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from textwrap import shorten
from threading import Event

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.completion import ThreadedCompleter
from prompt_toolkit.filters import has_completions, is_done, to_filter
from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    StyleAndTextTuples,
    fragment_list_width,
)
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    FloatContainer,
    HSplit,
    ScrollOffsets,
    Window,
)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.menus import CompletionsMenuControl
from prompt_toolkit.layout.processors import Processor, Transformation, TransformationInput
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from rich.console import Console, Group
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from coding_agent.branding import MODULE_NAME, PRODUCT_NAME
from coding_agent.controller import AgentController
from coding_agent.memory import MemoryError
from coding_agent.session import SessionError
from coding_agent.ui.cancel import EscapeMonitor
from coding_agent.ui.commands import COMMAND_BY_NAME, COMMAND_SPECS, normalize_command_name
from coding_agent.ui.completion import AgentCompleter
from coding_agent.ui.render import RichRenderer

ControllerFactory = Callable[[str | None], AgentController]

_PROMPT_STYLE = Style.from_dict(
    {
        "prompt": "bold #59b8ff bg:#202a38",
        "composer": "#eef3fa bg:#202a38",
        "composer-text": "#eef3fa bg:#202a38",
        "continuation": "#637083 bg:#202a38",
        "bottom-toolbar": "#637083 bg:#11161e noreverse",
        "bottom-toolbar.model": "bold #8ba7c9",
        "bottom-toolbar.accent": "#59b8ff",
        "placeholder": "#637083 italic",
        "completion-menu": "bg:#172033 #d7deea",
        "completion-menu.completion": "bg:#172033 #d7deea noreverse",
        "completion-menu.completion.current": "bg:#31558a #ffffff",
        "completion-menu.meta.completion": "bg:#172033 #9aa8ba noreverse",
        "completion-menu.meta.completion.current": "bg:#31558a #ffffff noreverse",
        "completion-menu.multi-column-meta": "bg:#172033 #9aa8ba noreverse",
    }
)

_PROMPT_NO_COLOR_STYLE = Style.from_dict(
    {
        "prompt": "bold",
        "composer": "",
        "composer-text": "",
        "continuation": "",
        "bottom-toolbar": "fg:default bg:default noreverse",
        "bottom-toolbar.model": "bold",
        "bottom-toolbar.accent": "",
        "placeholder": "italic",
        "completion-menu": "fg:default bg:default noreverse",
        "completion-menu.completion": "fg:default bg:default noreverse",
        "completion-menu.completion.current": "fg:default bg:default reverse",
        "completion-menu.meta.completion": "fg:default bg:default noreverse",
        "completion-menu.meta.completion.current": "fg:default bg:default reverse",
        "completion-menu.multi-column-meta": "fg:default bg:default noreverse",
    }
)


def _prompt_style() -> Style:
    return _PROMPT_NO_COLOR_STYLE if os.environ.get("NO_COLOR") else _PROMPT_STYLE


class _PromptBackgroundProcessor(Processor):
    """Apply the submitted-turn background while the user is still editing."""

    def apply_transformation(self, transformation_input: TransformationInput) -> Transformation:
        fragments: StyleAndTextTuples = []
        for fragment in transformation_input.fragments:
            if len(fragment) == 2:
                style, text = fragment
                fragments.append((f"{style} class:composer-text".strip(), text))
            else:
                style, text, handler = fragment
                fragments.append((f"{style} class:composer-text".strip(), text, handler))
        return Transformation(fragments)


def _continuation(width: int, line_number: int, soft_wrap_width: int) -> AnyFormattedText:
    del line_number, soft_wrap_width
    return [("class:continuation", " " * width)]


def _install_compact_composer(
    session: PromptSession[str],
) -> tuple[HSplit | None, Window | None]:
    """Install a compact editor with completion rows outside its background."""

    layout = getattr(session, "layout", None)
    if layout is None or not isinstance(layout.container, HSplit):
        return None, None
    original_root = layout.container
    if not original_root.children:
        return None, None
    main_wrapper = original_root.children[0]
    if not isinstance(main_wrapper, ConditionalContainer):
        return None, None
    main_input = main_wrapper.alternative_content
    if not isinstance(main_input, FloatContainer) or not isinstance(main_input.content, HSplit):
        return None, None

    editor = layout.current_window
    editor.height = Dimension(min=1)
    editor.style = "class:composer"
    editor.dont_extend_height = to_filter(True)
    composer = HSplit(
        [
            Window(height=1, char=" ", style="class:composer"),
            *main_input.content.children,
            Window(height=1, char=" ", style="class:composer"),
        ],
        style="class:composer",
    )

    def completion_height() -> Dimension:
        state = get_app().current_buffer.complete_state
        count = len(state.completions) if state is not None else 1
        rows = get_app().output.get_size().rows
        visible = min(count, max(1, rows // 3))
        return Dimension.exact(visible)

    completion_window = Window(
        content=CompletionsMenuControl(),
        height=completion_height,
        scroll_offsets=ScrollOffsets(top=1, bottom=1),
        right_margins=[ScrollbarMargin(display_arrows=True)],
        dont_extend_height=True,
        style="class:completion-menu",
    )
    completion_menu = ConditionalContainer(
        completion_window,
        filter=has_completions & ~is_done,
    )
    compact_layout = Layout(
        HSplit([composer, completion_menu, *original_root.children[1:]]),
        focused_element=editor,
    )
    session.layout = compact_layout
    session.app.layout = compact_layout
    return composer, completion_window


def _bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("c-j")
    @bindings.add("escape", "enter")
    def newline(event):  # type: ignore[no-untyped-def]
        event.current_buffer.insert_text("\n")

    @bindings.add("enter")
    def accept(event):  # type: ignore[no-untyped-def]
        event.current_buffer.validate_and_handle()

    @bindings.add("c-g")
    def editor(event):  # type: ignore[no-untyped-def]
        event.current_buffer.open_in_editor()

    @bindings.add("c-l")
    def clear(event):  # type: ignore[no-untyped-def]
        event.app.renderer.clear()

    return bindings


class InteractiveShell:
    def __init__(
        self,
        *,
        controller: AgentController,
        controller_factory: ControllerFactory,
        renderer: RichRenderer,
        history_file: Path,
    ) -> None:
        self.controller = controller
        self.controller_factory = controller_factory
        self.renderer = renderer
        self.console: Console = renderer.console
        if controller.skills is None:
            raise ValueError("interactive shell requires a skill registry")
        self.session: PromptSession[str] = PromptSession(
            history=FileHistory(str(history_file)),
            completer=self._completer(),
            key_bindings=_bindings(),
            multiline=True,
            complete_while_typing=True,
            complete_style=CompleteStyle.COLUMN,
            reserve_space_for_menu=0,
            enable_open_in_editor=True,
            input_processors=[_PromptBackgroundProcessor()],
            prompt_continuation=_continuation,
            bottom_toolbar=self._bottom_toolbar,
            placeholder=[("class:placeholder", "Describe a task or type /help")],
            style=_prompt_style(),
        )
        self.composer, self.completion_window = _install_compact_composer(self.session)
        self.renderer.set_viewport_width_provider(self._terminal_width)

    def _terminal_width(self) -> int:
        """Return prompt_toolkit's current visible terminal width."""

        output = getattr(self.session, "output", None)
        width: int | None = None
        if output is not None:
            with suppress(AttributeError, OSError, TypeError, ValueError):
                width = int(output.get_size().columns)
        width = max(1, width if width is not None else self.console.width)
        self.console.width = width
        return width

    def run(self) -> int:
        self.renderer.header(
            model=self.controller.settings.model.name,
            cwd=self.controller.settings.cwd.name,
            permissions=self.controller.approval.mode,
        )
        self.renderer.welcome()
        while True:
            try:
                value = self.session.prompt([("class:prompt", "› ")]).strip()
            except EOFError:
                self._session_handoff()
                return 0
            except KeyboardInterrupt:
                self.console.print("[yellow]已取消输入；Ctrl+D 退出。[/]")
                continue
            if not value:
                continue
            if value.startswith("/"):
                self.console.print()
                if self._slash(value):
                    self._session_handoff()
                    return 0
                continue
            self.renderer.start_turn_status(self._runtime_status)
            cancel_event = Event()
            try:
                with EscapeMonitor(
                    cancel_event,
                    enabled=lambda: self.renderer.accepts_escape_cancel,
                ):
                    self.controller.run_turn(value, cancel_event=cancel_event)
            finally:
                self.renderer.stop_turn_status()
            self.renderer.prompt_boundary()

    def _runtime_status(self) -> dict[str, object]:
        settings = self.controller.settings
        memory_enabled = bool(self.controller.memory and self.controller.memory.enabled)
        completed = sum(item.get("status") == "completed" for item in self.controller.working.plan)
        return {
            "model": settings.model.name,
            "max_steps": settings.agent.max_steps,
            "plan_completed": completed,
            "plan_total": len(self.controller.working.plan),
            "context_tokens": self.controller.last_context_tokens,
            "context_window": settings.agent.context_window,
            "memory_enabled": memory_enabled,
            "skills": ",".join(self.controller.working.active_skills),
        }

    def _session_handoff(self) -> None:
        session_id = self.controller.session_id
        workspace = self.controller.settings.cwd
        self.console.print(
            Text.assemble(
                ("session saved: ", "dim"),
                (session_id, "cyan"),
                "\n",
                ("resume: ", "dim"),
                f'python -m {MODULE_NAME} resume {session_id} --cwd "{workspace}"',
            )
        )

    def _bottom_toolbar(self):  # type: ignore[no-untyped-def]
        settings = self.controller.settings
        tokens = self.controller.last_context_tokens
        memory_enabled = bool(self.controller.memory and self.controller.memory.enabled)
        completed = sum(item.get("status") == "completed" for item in self.controller.working.plan)
        total = len(self.controller.working.plan)
        used = min(100, int(tokens * 100 / max(1, settings.agent.context_window)))
        candidates = [
            ("class:bottom-toolbar.model", f" {settings.model.name}"),
            ("class:bottom-toolbar", f" · {100 - used}% context left"),
            ("class:bottom-toolbar", f" · {settings.cwd.name}"),
        ]
        if total:
            candidates.append(("class:bottom-toolbar.accent", f" · plan {completed}/{total}"))
        candidates.append(("class:bottom-toolbar", f" · {self.controller.approval.mode}"))
        if memory_enabled:
            candidates.append(("class:bottom-toolbar", " · memory"))

        fragments: StyleAndTextTuples = []
        available = self._terminal_width()
        for candidate in candidates:
            if not fragments or fragment_list_width([*fragments, candidate]) <= available:
                fragments.append(candidate)
        return fragments

    def _slash(self, raw: str) -> bool:
        command, _, argument = raw.partition(" ")
        command = command.casefold()
        argument = argument.strip()
        if command not in COMMAND_BY_NAME:
            self.console.print(f"[red]unknown command: {command}[/]  Use /help to list commands.")
            return False
        if command == "/exit":
            if argument:
                self._usage(command)
                return False
            return True
        if command == "/help":
            self._help(argument)
        elif command == "/status":
            if not argument:
                self._status()
            else:
                self._usage(command)
        elif command == "/model":
            if argument:
                if len(argument.split()) != 1:
                    self._usage(command)
                    return False
                previous = self.controller.settings.model.name
                self.controller.settings.model.name = argument
                self.controller.model.model = argument
                if previous == argument:
                    self.console.print(f"model unchanged: [cyan]{argument}[/]")
                else:
                    self.console.print(
                        f"model changed: [dim]{previous}[/] → [cyan]{argument}[/] "
                        "[dim](current process; configuration unchanged)[/]"
                    )
            else:
                self.console.print(f"model: [cyan]{self.controller.settings.model.name}[/]")
            self._management_hint("change", "/model MODEL_ID", "current process only")
        elif command == "/permissions":
            if argument:
                if argument not in {"prompt", "auto", "read-only"}:
                    self._usage(command)
                    return False
                previous = self.controller.approval.mode
                changed = self.controller.approval.set_mode(argument)
                if changed:
                    self.console.print(
                        f"permissions changed: [dim]{previous}[/] → [cyan]{argument}[/]; "
                        "session grants revoked"
                    )
                else:
                    self.console.print(f"permissions unchanged: [cyan]{argument}[/]")
            else:
                descriptions = {
                    "prompt": "ask before mutations and commands",
                    "auto": "allow non-destructive operations without prompting",
                    "read-only": "deny mutations and commands that require approval",
                }
                mode = self.controller.approval.mode
                self.console.print(f"permissions: [cyan]{mode}[/] — {descriptions[mode]}")
                for name, description in descriptions.items():
                    marker = "•" if name == mode else " "
                    self.console.print(f"[dim]{marker} {name:<9} {description}[/]")
            self._management_hint(
                "change", "/permissions prompt|auto|read-only", "revokes session grants"
            )
        elif command == "/plan":
            if not argument:
                self.renderer.render_plan(self.controller.working.plan)
            else:
                self._usage(command)
        elif command == "/diff":
            if argument:
                self._usage(command)
            elif not self.controller.working.diffs:
                self.console.print(
                    "[dim]no applied edits recorded in this process; use git diff for all "
                    "workspace changes[/]"
                )
            else:
                self.console.print(
                    f"[bold]Applied edits in this process ({len(self.controller.working.diffs)})[/]"
                )
                for diff in self.controller.working.diffs:
                    self.renderer.render_diff(diff)
        elif command == "/raw":
            if argument not in {"", "on", "off"}:
                self._usage(command)
                return False
            if argument:
                self.renderer.raw = argument == "on"
            self.console.print(f"raw tool output: {'on' if self.renderer.raw else 'off'}")
            self._management_hint("set", "/raw on|off")
        elif command == "/compact":
            if argument:
                self._usage(command)
            else:
                before = self.controller.last_context_tokens
                summary = self.controller.manual_compact()
                after = self.controller.last_context_tokens
                self.console.print(
                    f"context compacted: {before} → {after} estimated request tokens; "
                    "transcript retained"
                    if summary
                    else f"context unchanged: {before} estimated request tokens (nothing eligible)"
                )
        elif command == "/clear":
            if not argument:
                self.console.clear()
            else:
                self._usage(command)
        elif command == "/new":
            if argument:
                self._usage(command)
            else:
                self._switch_controller(None)
        elif command == "/resume":
            if not argument:
                selected = self._choose_session()
                if selected:
                    self._switch_controller(selected)
            elif argument == self.controller.session_id:
                self.console.print(f"already using session: [cyan]{argument}[/]")
            else:
                self._switch_controller(argument)
        elif command == "/memory":
            self._memory(argument)
        elif command == "/skills":
            self._skills(argument)
        return False

    def _usage(self, command: str) -> None:
        spec = COMMAND_BY_NAME[command]
        self.console.print("usage: " + " | ".join(spec.usage))

    def _management_hint(self, label: str, command: str, note: str = "") -> None:
        line = Text.assemble((f"{label}: ", "dim"), (command, "bold cyan"))
        if note:
            line.append(f"  ({note})", style="dim")
        self.console.print(line)

    def _help(self, argument: str) -> None:
        if argument:
            name = normalize_command_name(argument)
            spec = COMMAND_BY_NAME.get(name)
            if spec is None:
                self.console.print(f"[red]unknown command: {argument}[/]")
                return
            self.console.print(Text(spec.name, style="bold cyan"))
            self.console.print(spec.description)
            for usage in spec.usage:
                self.console.print(Text.assemble(("  ", "dim"), (usage, "bold")))
            self.console.print(Text(spec.details, style="dim"))
            return
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(ratio=1)
        for spec in COMMAND_SPECS:
            table.add_row(spec.name, spec.description)
        self.console.print(Text("Slash commands", style="bold"))
        self.console.print(table)
        self.console.print("[dim]Use /help COMMAND for usage, scope, and side effects.[/]")

    def _status(self) -> None:
        memory = self.controller.memory
        skills = self.controller.skills
        tokens = self.controller.last_context_tokens
        completed = sum(item.get("status") == "completed" for item in self.controller.working.plan)
        project_resources = bool(
            self.controller.agents_instructions or (skills is not None and skills.include_repo)
        )
        self.renderer.status_table(
            [
                ("session", self.controller.session_id),
                ("model", self.controller.settings.model.name),
                ("workspace", str(self.controller.settings.cwd)),
                (
                    "permissions",
                    f"{self.controller.approval.mode} "
                    f"({self.controller.approval.session_grant_count} session grants)",
                ),
                ("project resources", "trusted and loaded" if project_resources else "not loaded"),
                (
                    "context",
                    f"{tokens}/{self.controller.settings.agent.context_window} "
                    "estimated request tokens",
                ),
                ("plan", f"{completed}/{len(self.controller.working.plan)} completed"),
                (
                    "memory",
                    "unavailable"
                    if memory is None
                    else f"{'on' if memory.enabled else 'off'} ({len(memory.list())} stored)",
                ),
                (
                    "skills",
                    "unavailable"
                    if skills is None
                    else f"{len(skills.catalog())} available; "
                    f"active: {', '.join(sorted(skills.active)) or 'none'}",
                ),
                ("raw tool output", "on" if self.renderer.raw else "off"),
            ]
        )

    def _switch_controller(self, session_id: str | None) -> None:
        previous = self.controller
        memory_enabled = bool(previous.memory and previous.memory.enabled)
        try:
            replacement = self.controller_factory(session_id)
        except SessionError as exc:
            self.console.print(f"[red]{exc}[/]")
            return
        replacement.approval.set_mode(previous.approval.mode)
        if replacement.memory is not None:
            replacement.memory.enabled = memory_enabled
        self.controller = replacement
        self.session.completer = self._completer()
        action = "new session" if session_id is None else "resumed session"
        self.console.print(
            Text.assemble(
                ("saved previous session: ", "dim"),
                (previous.session_id, "cyan"),
                "\n",
                (f"{action}: ", "dim"),
                (replacement.session_id, "cyan"),
                (" (session approvals reset)", "dim"),
            )
        )
        if session_id is not None:
            self._render_recent_context(replacement.conversation)

    def _render_recent_context(self, messages: list[dict[str, object]]) -> None:
        turns: list[tuple[str, list[str]]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            compact = " ".join(content.split())
            if role == "user":
                turns.append((compact, []))
            elif role == "assistant" and turns:
                turns[-1][1].append(compact)
        if not turns:
            self.console.print("[dim]no prior user conversation to preview[/]")
            return
        visible = turns[-3:]
        self.console.print(
            Text.assemble(("Recent context", "bold"), (f"  last {len(visible)} turns", "dim"))
        )
        for user_text, assistant_messages in visible:
            user_prefix = "› you     "
            user_width = max(5, self._terminal_width() - get_cwidth(user_prefix))
            user_summary = shorten(user_text, width=user_width, placeholder="…")
            self.console.print(Text.assemble((user_prefix, "bold cyan"), user_summary))
            if assistant_messages:
                assistant_prefix = f"  {PRODUCT_NAME}  "
                assistant_width = max(5, self._terminal_width() - get_cwidth(assistant_prefix))
                assistant_summary = shorten(
                    assistant_messages[-1], width=assistant_width, placeholder="…"
                )
                self.console.print(Text.assemble((assistant_prefix, "dim"), assistant_summary))
            else:
                self.console.print("[dim]  no assistant response recorded[/]")

    def _choose_session(self) -> str | None:
        workspace = self.controller.settings.cwd.resolve()
        candidates: list[dict[str, object]] = []
        for item in self.controller.sessions.list():
            if item.get("id") == self.controller.session_id:
                continue
            recorded_workspace = str(item.get("workspace", ""))
            if not recorded_workspace:
                continue
            try:
                if Path(recorded_workspace).resolve() != workspace:
                    continue
            except OSError:
                continue
            candidates.append(item)
            if len(candidates) >= 10:
                break
        if not candidates:
            self.console.print("[dim]no other resumable sessions for this workspace[/]")
            self._management_hint("create", "/new")
            return None

        self.console.print(Text("Recent sessions", style="bold"))
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", width=3, justify="right")
        table.add_column(style="dim", width=12, no_wrap=True)
        table.add_column(ratio=1)
        for index, item in enumerate(candidates, 1):
            updated = self._session_time(str(item.get("updated_at", "")))
            title = " ".join(str(item.get("title", "")).split())
            title = title or "(untitled session)"
            session_id = str(item["id"])
            model = str(item.get("model", ""))
            details = Text.assemble(
                (title, ""),
                (f"\n{session_id[:12]}", "dim"),
                (f" · {model}" if model else "", "dim"),
            )
            table.add_row(str(index), updated, details)
        self.console.print(table)
        choice = Prompt.ask(
            "Resume which session?",
            choices=[*(str(index) for index in range(1, len(candidates) + 1)), "q"],
            default="q",
            console=self.console,
        )
        if choice == "q":
            self.console.print("[dim]resume cancelled[/]")
            return None
        try:
            return str(candidates[int(choice) - 1]["id"])
        except (ValueError, IndexError):
            self.console.print(f"[red]invalid session selection: {choice}[/]")
            return None

    @staticmethod
    def _session_time(value: str) -> str:
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%m-%d %H:%M")
        except ValueError:
            return value[:12] or "unknown"

    def _memory(self, argument: str) -> None:
        action, _, value = argument.partition(" ")
        action = action.casefold()
        value = value.strip()
        store = self.controller.memory
        if store is None:
            self.console.print("[dim]project memory is unavailable[/]")
            return
        try:
            if action in {"on", "off"}:
                if value:
                    self._usage("/memory")
                    return
                store.enabled = action == "on"
                self.console.print(
                    f"project memory: {action} [dim](current process; stored records unchanged)[/]"
                )
                self._memory_controls()
            elif action in {"list", ""}:
                if value:
                    self._usage("/memory")
                    return
                records = store.list()
                if not records:
                    self.console.print("[dim]no project memories[/]")
                    self._memory_controls()
                    return
                self.console.print(
                    f"[bold]Project memories ({len(records)}; injection "
                    f"{'on' if store.enabled else 'off'})[/]"
                )
                for record in records:
                    self.console.print(f"{record.id} [{record.kind.value}] {record.content}")
                self._memory_controls()
            elif action == "remember":
                if not value:
                    self._usage("/memory")
                    return
                record = store.remember(content=value, session_id=self.controller.session_id)
                self.console.print(f"remembered for this project: [cyan]{record.id}[/]")
                self._memory_controls()
            elif action == "forget":
                if not value:
                    self._usage("/memory")
                    return
                self.console.print(
                    f"forgotten: {value}" if store.forget(value) else f"memory not found: {value}"
                )
                self._memory_controls()
            elif action == "clear":
                if value != "confirm":
                    count = len(store.list())
                    self.console.print(
                        f"[yellow]clear would remove {count} project memories; "
                        "run /memory clear confirm to continue[/]"
                    )
                    return
                store.clear()
                self.console.print("project memory cleared (0 stored records)")
                self._memory_controls()
            else:
                self._usage("/memory")
        except MemoryError as exc:
            self.console.print(f"[red]{exc}[/]")

    def _memory_controls(self) -> None:
        self._management_hint("toggle", "/memory on|off", "current process")
        self._management_hint("manage", "/memory remember TEXT · forget ID · clear confirm")

    def _skills(self, argument: str) -> None:
        action, _, value = argument.partition(" ")
        action = action.casefold()
        value = value.strip()
        registry = self.controller.skills
        if registry is None:
            self.console.print("[dim]skills are unavailable[/]")
            return
        if action in {"", "list"}:
            if value:
                self._usage("/skills")
                return
        elif action == "reload":
            if value:
                self._usage("/skills")
                return
            registry.discover(include_repo=registry.include_repo)
            self.console.print(
                f"skills reloaded: {len(registry.catalog())} discovered; "
                "session disable choices preserved"
            )
        elif action in {"enable", "disable"}:
            if not value:
                self._usage("/skills")
                return
            name = value.removeprefix("$")
            try:
                self.controller.set_skill_enabled(name, action == "enable")
            except ValueError as exc:
                self.console.print(f"[red]{exc}[/]")
                return
            self.console.print(f"skill ${name} {action}d for this session")
            self._skills_controls()
            return
        elif action == "search":
            if not value:
                self._usage("/skills")
                return
        else:
            self._usage("/skills")
            return
        query = value.casefold() if action == "search" else ""
        visible: list[dict[str, object]] = []
        for item in registry.catalog():
            if query and query not in (item["name"] + " " + item["description"]).casefold():
                continue
            visible.append(item)
        self._render_skills(visible, query=value if action == "search" else "")
        if not visible and action == "search":
            self.console.print(f"[dim]no skills matched: {value}[/]")
        self._skills_controls()
        if registry.diagnostics:
            self.console.print(Text("Skill diagnostics", style="bold yellow"))
        for diagnostic in registry.diagnostics:
            self.console.print(f"[yellow]{diagnostic}[/]")

    @staticmethod
    def _skill_summary(description: object, *, width: int) -> str:
        value = " ".join(str(description).split())
        folded = value.casefold()
        cut_points = [
            folded.find(marker)
            for marker in (" use for:", " do not use for:", " triggers on:", " access:")
            if folded.find(marker) >= 0
        ]
        if cut_points:
            value = value[: min(cut_points)].rstrip(" .;:") + "."
        return shorten(value, width=width, placeholder="…")

    def _render_skills(self, items: list[dict[str, object]], *, query: str) -> None:
        registry = self.controller.skills
        active = registry.active if registry is not None else set()
        enabled = sum(bool(item["enabled"]) for item in items)
        visible_active = sum(str(item["name"]) in active for item in items)
        title = "Skill search" if query else "Skills"
        detail = f"{len(items)} shown · {enabled} enabled · {visible_active} active"
        if query:
            detail += f" · query: {query}"
        self.console.print(Text.assemble((title, "bold"), (f"  {detail}", "dim")))
        if not items:
            return
        table = Table.grid(padding=(0, 1))
        table.add_column(width=2, no_wrap=True)
        table.add_column(ratio=1)
        for item in items:
            name = str(item["name"])
            is_enabled = bool(item["enabled"])
            marker = Text("✓" if is_enabled else "×", style="green" if is_enabled else "red")
            labels = [str(item["source"]), "enabled" if is_enabled else "disabled"]
            if name in active:
                labels.append("active")
            heading = Text.assemble(
                (f"${name}", "bold cyan"),
                ("  " + " · ".join(labels), "dim"),
            )
            summary_width = max(5, self._terminal_width() - 4)
            summary = Text(
                self._skill_summary(item["description"], width=summary_width),
                style="dim",
            )
            table.add_row(marker, Group(heading, summary))
        self.console.print(table)

    def _skills_controls(self) -> None:
        self._management_hint("find", "/skills search QUERY")
        self._management_hint("manage", "/skills enable|disable NAME · /skills reload")
        self._management_hint("activate", "$NAME followed by your task")

    def _completer(self) -> ThreadedCompleter:
        skills = self.controller.skills
        if skills is None:
            raise ValueError("interactive shell requires a skill registry")
        return ThreadedCompleter(AgentCompleter(self.controller.settings.cwd, skills))
