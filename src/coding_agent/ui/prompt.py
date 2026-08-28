from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console

from coding_agent.context import estimate_tokens
from coding_agent.controller import AgentController
from coding_agent.memory import MemoryError
from coding_agent.session import SessionError
from coding_agent.ui.completion import SLASH_COMMANDS, AgentCompleter
from coding_agent.ui.render import RichRenderer

ControllerFactory = Callable[[str | None], AgentController]


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
            completer=AgentCompleter(controller.settings.cwd, controller.skills),
            key_bindings=_bindings(),
            multiline=True,
            complete_while_typing=True,
            enable_open_in_editor=True,
        )

    def run(self) -> int:
        self.renderer.header(
            model=self.controller.settings.model.name,
            cwd=self.controller.settings.cwd.name,
            permissions=self.controller.approval.mode,
        )
        self.console.print("[dim]输入任务，/help 查看命令；Ctrl+D 退出。[/]")
        while True:
            try:
                value = self.session.prompt("› ").strip()
            except EOFError:
                return 0
            except KeyboardInterrupt:
                self.console.print("[yellow]已取消输入；Ctrl+D 退出。[/]")
                continue
            if not value:
                continue
            if value.startswith("/"):
                if self._slash(value):
                    return 0
                continue
            result = self.controller.run_turn(value)
            self._footer(result.tool_steps)

    def _footer(self, steps: int) -> None:
        tokens = estimate_tokens(self.controller.conversation)
        settings = self.controller.settings
        memory_enabled = bool(self.controller.memory and self.controller.memory.enabled)
        self.console.print(
            "[dim]"
            f"{settings.model.name} | {steps}/{settings.agent.max_steps} steps | "
            f"context {tokens}/{settings.agent.context_window} | "
            f"memory {'on' if memory_enabled else 'off'} | "
            f"skills {','.join(self.controller.working.active_skills) or '-'}"
            "[/]"
        )

    def _slash(self, raw: str) -> bool:
        command, _, argument = raw.partition(" ")
        argument = argument.strip()
        if command == "/exit":
            return True
        if command == "/help":
            self.console.print("  ".join(SLASH_COMMANDS))
        elif command == "/status":
            memory_enabled = bool(self.controller.memory and self.controller.memory.enabled)
            self.renderer.status_table(
                [
                    ("session", self.controller.session_id),
                    ("model", self.controller.settings.model.name),
                    ("cwd", str(self.controller.settings.cwd)),
                    ("permissions", self.controller.approval.mode),
                    ("memory", "on" if memory_enabled else "off"),
                ]
            )
        elif command == "/model":
            if argument:
                self.controller.settings.model.name = argument
                self.controller.model.model = argument
            self.console.print(self.controller.settings.model.name)
        elif command == "/permissions":
            if argument:
                if argument not in {"prompt", "auto", "read-only"}:
                    self.console.print("[red]use prompt, auto, or read-only[/]")
                    return False
                self.controller.approval.mode = argument
            self.console.print(self.controller.approval.mode)
        elif command == "/plan":
            self.renderer.render_plan(self.controller.working.plan)
        elif command == "/diff":
            if not self.controller.working.diffs:
                self.console.print("[dim]no edits in this process[/]")
            for diff in self.controller.working.diffs:
                self.console.print(diff, markup=False)
        elif command == "/raw":
            self.renderer.raw = not self.renderer.raw
            self.console.print(f"raw tool output: {'on' if self.renderer.raw else 'off'}")
        elif command == "/compact":
            summary = self.controller.manual_compact()
            self.console.print("context compacted" if summary else "context is already compact")
        elif command == "/clear":
            self.console.clear()
        elif command == "/new":
            self.controller = self.controller_factory(None)
            self.session.completer = self._completer()
            self.console.print(f"new session: {self.controller.session_id}")
        elif command == "/resume":
            if not argument:
                self.console.print("usage: /resume SESSION_ID")
            else:
                try:
                    self.controller = self.controller_factory(argument)
                    self.session.completer = self._completer()
                    self.console.print(f"resumed: {argument}")
                except SessionError as exc:
                    self.console.print(f"[red]{exc}[/]")
        elif command == "/memory":
            self._memory(argument)
        elif command == "/skills":
            self._skills(argument)
        else:
            self.console.print(f"[red]unknown command: {command}[/]")
        return False

    def _memory(self, argument: str) -> None:
        action, _, value = argument.partition(" ")
        store = self.controller.memory
        if store is None:
            self.console.print("[dim]project memory is unavailable[/]")
            return
        try:
            if action in {"on", "off"}:
                store.enabled = action == "on"
                self.console.print(f"memory {action}")
            elif action == "list" or not action:
                records = store.list()
                if not records:
                    self.console.print("[dim]no project memories[/]")
                for record in records:
                    self.console.print(f"{record.id} [{record.kind.value}] {record.content}")
            elif action == "remember":
                record = store.remember(content=value, session_id=self.controller.session_id)
                self.console.print(f"remembered {record.id}")
            elif action == "forget":
                self.console.print("forgotten" if store.forget(value) else "memory not found")
            elif action == "clear":
                store.clear()
                self.console.print("project memory cleared")
            else:
                self.console.print("usage: /memory on|off|list|remember TEXT|forget ID|clear")
        except MemoryError as exc:
            self.console.print(f"[red]{exc}[/]")

    def _skills(self, argument: str) -> None:
        action, _, value = argument.partition(" ")
        registry = self.controller.skills
        if registry is None:
            self.console.print("[dim]skills are unavailable[/]")
            return
        if action == "reload":
            registry.discover(include_repo=registry.include_repo)
        elif action in {"enable", "disable"} and value:
            try:
                registry.set_enabled(value, action == "enable")
            except ValueError as exc:
                self.console.print(f"[red]{exc}[/]")
                return
        query = value.casefold() if action == "search" else ""
        for item in registry.catalog():
            if query and query not in (item["name"] + " " + item["description"]).casefold():
                continue
            marker = "✓" if item["enabled"] else "×"
            self.console.print(
                f"{marker} ${item['name']} [dim]({item['source']})[/] {item['description']}"
            )
        for diagnostic in registry.diagnostics:
            self.console.print(f"[yellow]{diagnostic}[/]")

    def _completer(self) -> AgentCompleter:
        skills = self.controller.skills
        if skills is None:
            raise ValueError("interactive shell requires a skill registry")
        return AgentCompleter(self.controller.settings.cwd, skills)
