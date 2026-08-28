from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.json import JSON
from rich.live import Live
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from coding_agent.branding import COMMAND_NAME, PRODUCT_NAME
from coding_agent.events import AgentEvent, AgentState, EventKind

RuntimeStatusProvider = Callable[[], dict[str, Any]]


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
        self.console = console or Console(no_color=no_color, soft_wrap=False)
        self.raw = raw
        self._stream_buffer: list[str] = []
        self._live: Live | None = None
        self._turn_live: Live | None = None
        self._runtime_status_provider: RuntimeStatusProvider | None = None
        self._runtime_values: dict[str, Any] = {}
        self._runtime_state = AgentState.IDLE
        self._runtime_step = 0
        self._runtime_tool = ""
        self._spinner: Spinner | None = None
        self._last_plan: list[dict[str, Any]] = []
        self._section_gap = False

    def _width(self) -> int:
        return max(32, min(self.console.width, 100))

    def _response_width(self) -> int:
        return max(30, self._width() - 2)

    @staticmethod
    def _indented(renderable: RenderableType) -> Padding:
        return Padding(renderable, (0, 0, 0, 2))

    def output(self, renderable: RenderableType, *, soft_wrap: bool = False) -> None:
        """Print non-user conversation output on the shared response inset."""

        self.console.print(self._indented(renderable), soft_wrap=soft_wrap)
        self._section_gap = False

    def section_break(self, *, force: bool = False) -> None:
        """Leave one blank line before the next semantic conversation block."""

        if self._section_gap and not force:
            return
        self.console.print()
        self._section_gap = True

    @property
    def accepts_escape_cancel(self) -> bool:
        return self._runtime_state is not AgentState.AWAITING_APPROVAL

    def _symbol(self, value: str, fallback: str) -> str:
        try:
            value.encode(self.console.encoding or "utf-8")
        except (LookupError, UnicodeEncodeError):
            return fallback
        return value

    def header(self, *, model: str, cwd: str, permissions: str) -> None:
        title = Text(f" {PRODUCT_NAME} ", style="bold white on #31558a")
        detail = Text()
        detail.append("model: ", style="dim")
        detail.append(model)
        detail.append("  cwd: ", style="dim")
        detail.append(cwd)
        detail.append("  permissions: ", style="dim")
        detail.append(permissions)
        self.console.print(
            Panel(
                detail,
                title=title,
                subtitle=f" {COMMAND_NAME} ",
                width=self._width(),
                border_style="#6f87aa",
                padding=(0, 1),
            )
        )

    def welcome(self) -> None:
        self.console.print(
            Text.assemble(
                (self._symbol("›", ">") + " ", "bold cyan"),
                ("输入任务", "bold"),
                ("  /help 查看命令 · Ctrl+J 换行 · Esc 取消运行 · Ctrl+D 退出", "dim"),
            )
        )

    def start_turn_status(self, provider: RuntimeStatusProvider) -> None:
        """Keep an execution status bar visible while prompt_toolkit is suspended."""
        self._end_stream()
        if self._turn_live is not None:
            self._turn_live.stop()
            self._turn_live = None
        self._runtime_status_provider = provider
        self._runtime_values = provider()
        self._runtime_state = AgentState.THINKING
        self._runtime_step = 0
        self._runtime_tool = ""
        self._last_plan = []
        self.resume_turn_status()

    def pause_turn_status(self) -> bool:
        """Temporarily remove the live footer so an interactive prompt stays visible."""

        self._end_stream()
        if self._turn_live is None:
            return False
        self._turn_live.stop()
        self._turn_live = None
        return True

    def resume_turn_status(self) -> None:
        if (
            self._runtime_status_provider is None
            or self._turn_live is not None
            or not self.console.is_terminal
        ):
            return
        self._spinner = Spinner("line", text=self._runtime_status_text(), style="cyan")
        self._turn_live = Live(
            self._turn_renderable(),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        )
        self._turn_live.start(refresh=True)

    def stop_turn_status(self) -> None:
        self._end_stream()
        if self._turn_live is not None:
            self._turn_live.stop()
            self._turn_live = None
        self._runtime_status_provider = None
        self._runtime_values = {}
        self._runtime_state = AgentState.IDLE
        self._runtime_step = 0
        self._runtime_tool = ""
        self._spinner = None

    def _runtime_status_text(self) -> Text:
        values = self._runtime_values
        labels = {
            AgentState.THINKING: "Working",
            AgentState.PLANNING: "Planning",
            AgentState.TOOL_PENDING: "Preparing",
            AgentState.AWAITING_APPROVAL: "Waiting for approval",
            AgentState.EXECUTING: "Running",
            AgentState.OBSERVING: "Reviewing result",
            AgentState.COMPLETED: "Completed",
            AgentState.FAILED: "Failed",
            AgentState.CANCELLED: "Cancelled",
        }
        line = Text(labels.get(self._runtime_state, "Working"), style="bold")
        if self._runtime_tool and self._runtime_state in {
            AgentState.TOOL_PENDING,
            AgentState.EXECUTING,
        }:
            line.append(f" {self._runtime_tool}", style="cyan")
        line.append(f" · step {self._runtime_step}/{values.get('max_steps', '-')}", style="dim")
        plan_total = int(values.get("plan_total", 0))
        if plan_total:
            line.append(
                f" · plan {values.get('plan_completed', 0)}/{plan_total}",
                style="dim",
            )
        if self.console.width >= 80:
            window = max(1, int(values.get("context_window", 1)))
            used = min(100, int(int(values.get("context_tokens", 0)) * 100 / window))
            line.append(f" · {100 - used}% context left", style="dim")
        line.truncate(max(1, self.console.width - 3), overflow="ellipsis")
        return line

    def _turn_renderable(self) -> RenderableType:
        status: RenderableType
        if self._runtime_state is AgentState.AWAITING_APPROVAL:
            status = Text.assemble(("! ", "bold yellow"), self._runtime_status_text())
        elif self._spinner is not None:
            self._spinner.update(text=self._runtime_status_text())
            status = self._spinner
        else:
            status = Text.assemble(("* ", "cyan"), self._runtime_status_text())
        if self._stream_buffer:
            return self._indented(Group(Markdown("".join(self._stream_buffer)), status))
        return self._indented(status)

    @staticmethod
    def _assistant_markdown(content: str) -> Padding:
        """Separate assistant prose from the tool timeline with a stable left inset."""

        return Padding(Markdown(content), (0, 0, 0, 2))

    def _refresh_turn_status(self, *, refresh_metrics: bool = True) -> None:
        if refresh_metrics and self._runtime_status_provider is not None:
            self._runtime_values = self._runtime_status_provider()
        if self._turn_live is not None:
            self._turn_live.update(self._turn_renderable(), refresh=True)

    def _end_stream(self) -> None:
        if not self._stream_buffer:
            return
        content = "".join(self._stream_buffer)
        self._stream_buffer.clear()
        if self._turn_live is not None:
            self._refresh_turn_status(refresh_metrics=False)
            if content.strip():
                self.console.print(self._assistant_markdown(content))
            return
        if self._live is not None:
            self._live.update(self._assistant_markdown(content), refresh=True)
            self._live.stop()
            self._live = None
            return
        if content.strip():
            self.console.print(self._assistant_markdown(content))

    def handle(self, event: AgentEvent) -> None:
        if event.kind is EventKind.TEXT:
            delta = str(event.data.get("delta", ""))
            if delta and not self._stream_buffer:
                self.section_break()
            if delta:
                self._section_gap = False
            self._stream_buffer.append(delta)
            if self._turn_live is not None:
                self._refresh_turn_status(refresh_metrics=False)
            elif self.console.is_terminal:
                rendered = self._assistant_markdown("".join(self._stream_buffer))
                if self._live is None:
                    self._live = Live(
                        rendered,
                        console=self.console,
                        refresh_per_second=12,
                        transient=False,
                    )
                    self._live.start(refresh=True)
                else:
                    self._live.update(rendered, refresh=True)
            return
        self._end_stream()
        if event.state is not None:
            self._runtime_state = event.state
        if event.kind is EventKind.STATE:
            step = event.data.get("step")
            if isinstance(step, int):
                self._runtime_step = step
            tool = event.data.get("tool")
            self._runtime_tool = str(tool) if tool else ""
        elif event.kind is EventKind.PLAN:
            self.render_plan_update(event.data.get("plan", []))
        elif event.kind is EventKind.TOOL_CALL:
            self.section_break()
            name = str(event.data.get("name", "tool"))
            arguments = event.data.get("arguments", {})
            subject = self._subject(arguments)
            self.output(
                Text.assemble(
                    (self._symbol("•", "*") + " ", "cyan"),
                    (name, "bold #d7deea"),
                    (subject, "dim"),
                )
            )
            if self.raw:
                self.output(JSON(json.dumps(arguments, ensure_ascii=False, default=str)))
        elif event.kind is EventKind.TOOL_RESULT:
            result = event.data.get("result", {})
            ok = bool(result.get("ok"))
            icon = self._symbol("✓", "+") if ok else self._symbol("✗", "x")
            style = "green" if ok else "red"
            self.output(
                Text.assemble(
                    (f"{icon} ", style),
                    (
                        str(result.get("summary", "")),
                        "dim" if ok else "red",
                    ),
                )
            )
            if self.raw and result.get("data"):
                self.output(JSON(json.dumps(result["data"], ensure_ascii=False, default=str)))
            self.section_break()
        elif event.kind is EventKind.APPROVAL and "request" in event.data:
            self.section_break()
            request = event.data["request"]
            diff = request.get("diff")
            action = str(request.get("action", "operation"))
            subject = str(request.get("subject", ""))
            content: list[RenderableType] = [
                Text(str(request.get("summary", "approval required")), style="bold"),
            ]
            if diff:
                content.extend([Text(""), self.diff_text(str(diff))])
            self.output(
                Panel(
                    Group(*content),
                    title="Approval required",
                    subtitle="1 allow once · 2 allow session · 3 deny",
                    border_style="yellow",
                    width=self._response_width(),
                )
            )
            self.output(
                Text.assemble(
                    ("action  ", "dim"),
                    (action, "yellow"),
                    ("   target  ", "dim"),
                    subject,
                )
            )
        elif event.kind is EventKind.ERROR:
            self.section_break()
            self.output(
                Panel(
                    str(event.data.get("message", "error")),
                    title="错误",
                    border_style="red",
                    width=self._response_width(),
                )
            )
        elif event.kind is EventKind.WARNING:
            self.section_break()
            self.output(f"[yellow]warning:[/] {event.data.get('message', '')}")
        elif event.kind is EventKind.COMPACT:
            self.section_break()
            self.output(
                f"[dim]context compacted from {event.data.get('tokens_before', '?')} tokens[/]"
            )
        elif event.kind is EventKind.SKILL:
            self.section_break()
            self.output(f"[magenta]skill:[/] {event.data.get('name')} activated")
            self.section_break()
        elif event.kind is EventKind.DONE:
            self.section_break()
            state = event.state or AgentState.FAILED
            icon, style = {
                AgentState.COMPLETED: ("✓", "green"),
                AgentState.CANCELLED: ("■", "yellow"),
            }.get(state, ("✗", "red"))
            icon = self._symbol(icon, "!" if state is AgentState.CANCELLED else "x")
            reason = str(event.data.get("reason", ""))
            if state is AgentState.COMPLETED and reason == "assistant completed":
                reason = ""
            self.output(
                Text.assemble(
                    (f"{icon} {state.value}", f"bold {style}"),
                    (f"  {reason}" if reason else "", "dim"),
                )
            )
            self.section_break()
        self._refresh_turn_status()

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
        table = Table.grid(padding=(0, 1))
        table.add_column(width=2, no_wrap=True)
        table.add_column(ratio=1)
        if not plan:
            table.add_row(self._symbol("○", "o"), Text("计划为空", style="dim"))
        for item in plan:
            status = str(item.get("status", ""))
            icon, style = {
                "completed": ("✓", "green"),
                "in_progress": ("●", "cyan"),
                "pending": ("○", "dim"),
            }.get(status, ("?", "yellow"))
            icon = self._symbol(icon, {"completed": "+", "in_progress": "*"}.get(status, "o"))
            table.add_row(Text(icon, style=style), Text(str(item.get("step", ""))))
        self.output(Group(Text("Plan", style="bold"), table))

    def render_plan_update(self, plan: list[dict[str, Any]]) -> None:
        previous = self._last_plan
        self._last_plan = [dict(item) for item in plan]
        if not previous or [item.get("step") for item in previous] != [
            item.get("step") for item in plan
        ]:
            self.section_break()
            self.render_plan(plan)
            self.section_break()
            return
        separated = False
        for old, new in zip(previous, plan, strict=True):
            if old.get("status") == new.get("status"):
                continue
            status = str(new.get("status", ""))
            icon, style = {
                "completed": (self._symbol("✓", "+"), "green"),
                "in_progress": (self._symbol("•", "*"), "cyan"),
                "pending": (self._symbol("○", "o"), "dim"),
            }.get(status, ("?", "yellow"))
            if not separated:
                self.section_break()
                separated = True
            self.output(Text.assemble((f"{icon} ", style), str(new.get("step", ""))))
        if separated:
            self.section_break()

    @staticmethod
    def diff_text(diff: str) -> Text:
        rendered = Text()
        for line in diff.splitlines(keepends=True):
            if line.startswith("+++") or line.startswith("---"):
                style = "bold #d7deea on #28303d"
            elif line.startswith("+"):
                style = "#9ee6b0 on #173522"
            elif line.startswith("-"):
                style = "#ffb3b3 on #3a1c22"
            elif line.startswith("@@"):
                style = "bold #d9b8ff on #30243d"
            else:
                style = "#c5ccd8"
            rendered.append(line, style=style)
        if diff and not diff.endswith("\n"):
            rendered.append("\n")
        return rendered

    def render_diff(self, diff: str) -> None:
        self.output(self.diff_text(diff), soft_wrap=False)

    def markdown(self, content: str) -> None:
        self.output(Markdown(content))

    def status_table(self, rows: list[tuple[str, str]]) -> None:
        table = Table(show_header=False, box=None)
        for key, value in rows:
            table.add_row(Text(key, style="dim"), value)
        self.output(table)
