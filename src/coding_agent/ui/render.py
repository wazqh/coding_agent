from __future__ import annotations

import json
import os
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from coding_agent.events import AgentEvent, AgentState, EventKind


class JsonlRenderer:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(color_system=None, soft_wrap=True)

    def handle(self, event: AgentEvent) -> None:
        self.console.print(event.model_dump_json(), markup=False, highlight=False)


class RichRenderer:
    def __init__(
        self,
        *,
        console: Console | None = None,
        raw: bool = False,
    ) -> None:
        no_color = bool(os.environ.get("NO_COLOR"))
        self.console = console or Console(no_color=no_color, soft_wrap=True)
        self.raw = raw
        self._streaming_text = False

    def header(self, *, model: str, cwd: str, permissions: str) -> None:
        width = max(32, min(self.console.width, 100))
        title = Text(" coding-agent ", style="bold white on #3b4f73")
        detail = Text()
        detail.append("model: ", style="dim")
        detail.append(model)
        detail.append("  cwd: ", style="dim")
        detail.append(cwd)
        detail.append("  permissions: ", style="dim")
        detail.append(permissions)
        self.console.print(Panel(detail, title=title, width=width, border_style="#6f87aa"))

    def _end_stream(self) -> None:
        if self._streaming_text:
            self.console.print()
            self._streaming_text = False

    def handle(self, event: AgentEvent) -> None:
        if event.kind is EventKind.TEXT:
            self.console.print(
                str(event.data.get("delta", "")),
                end="",
                markup=False,
                highlight=False,
            )
            self._streaming_text = True
            return
        self._end_stream()
        if event.kind is EventKind.PLAN:
            self.render_plan(event.data.get("plan", []))
        elif event.kind is EventKind.TOOL_CALL:
            name = str(event.data.get("name", "tool"))
            arguments = event.data.get("arguments", {})
            subject = self._subject(arguments)
            self.console.print(Text.assemble(("● ", "cyan"), (name, "bold"), (subject, "dim")))
            if self.raw:
                self.console.print_json(json.dumps(arguments, ensure_ascii=False))
        elif event.kind is EventKind.TOOL_RESULT:
            result = event.data.get("result", {})
            ok = bool(result.get("ok"))
            icon = "✓" if ok else "✗"
            style = "green" if ok else "red"
            self.console.print(
                Text.assemble((f"{icon} ", style), (str(result.get("summary", "")), style))
            )
            if self.raw and result.get("data"):
                self.console.print_json(json.dumps(result["data"], ensure_ascii=False, default=str))
        elif event.kind is EventKind.APPROVAL and "request" in event.data:
            request = event.data["request"]
            diff = request.get("diff")
            if diff:
                self.console.print(Syntax(diff, "diff", theme="ansi_dark", word_wrap=True))
            self.console.print(
                Panel(
                    Text(str(request.get("summary", "approval required"))),
                    title="等待批准",
                    border_style="yellow",
                )
            )
        elif event.kind is EventKind.ERROR:
            self.console.print(Panel(str(event.data.get("message", "error")), border_style="red"))
        elif event.kind is EventKind.WARNING:
            self.console.print(f"[yellow]warning:[/] {event.data.get('message', '')}")
        elif event.kind is EventKind.COMPACT:
            self.console.print(
                f"[dim]context compacted from {event.data.get('tokens_before', '?')} tokens[/]"
            )
        elif event.kind is EventKind.SKILL:
            self.console.print(f"[magenta]skill:[/] {event.data.get('name')} activated")
        elif event.kind is EventKind.DONE:
            state = event.state or AgentState.FAILED
            style = {
                AgentState.COMPLETED: "green",
                AgentState.CANCELLED: "yellow",
            }.get(state, "red")
            self.console.print(f"[{style}]{state.value}:[/] {event.data.get('reason', '')}")

    @staticmethod
    def _subject(arguments: Any) -> str:
        if not isinstance(arguments, dict):
            return ""
        for key in ("path", "command", "name", "pattern"):
            if key in arguments:
                value = str(arguments[key]).replace("\n", " ")
                return "  " + value[:100]
        return ""

    def render_plan(self, plan: list[dict[str, Any]]) -> None:
        self.console.print("[bold]Plan[/]")
        for item in plan:
            status = str(item.get("status", ""))
            icon, style = {
                "completed": ("✓", "green"),
                "in_progress": ("●", "cyan"),
                "pending": ("○", "dim"),
            }.get(status, ("?", "yellow"))
            self.console.print(Text.assemble((f"  {icon} ", style), str(item.get("step", ""))))

    def markdown(self, content: str) -> None:
        self.console.print(Markdown(content))

    def status_table(self, rows: list[tuple[str, str]]) -> None:
        table = Table(show_header=False, box=None)
        for key, value in rows:
            table.add_row(Text(key, style="dim"), value)
        self.console.print(table)
