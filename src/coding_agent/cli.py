from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from platformdirs import user_data_path
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from coding_agent import __version__
from coding_agent.branding import COMMAND_NAME, PRODUCT_NAME
from coding_agent.config import ConfigError, load_settings
from coding_agent.controller import AgentController
from coding_agent.memory import MemoryStore
from coding_agent.model_client import ModelClient
from coding_agent.project import TrustManager, load_agents_instructions
from coding_agent.safety.approval import ApprovalDecision, ApprovalPolicy, ApprovalRequest
from coding_agent.session import SessionError, SessionStore
from coding_agent.skills import SkillRegistry
from coding_agent.tools.registry import default_registry
from coding_agent.ui.prompt import ControllerFactory, InteractiveShell
from coding_agent.ui.render import JsonlRenderer, RichRenderer

app = typer.Typer(
    name=COMMAND_NAME,
    help=f"{PRODUCT_NAME} — a safe, local-first CLI coding agent.",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
)


def _data_dir() -> Path:
    override = os.environ.get("CODING_AGENT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(user_data_path("coding-agent", "forge", ensure_exists=True))


def _resolve_trust(
    workspace: Path,
    data_dir: Path,
    *,
    interactive: bool,
    trust_project: bool,
    console: Console,
) -> bool:
    manager = TrustManager(data_dir)
    status = manager.status(workspace)
    if not status.has_resources:
        return False
    if status.trusted or trust_project:
        return True
    if not interactive:
        return False
    console.print(
        f"[yellow]{PRODUCT_NAME} found AGENTS.md, coding-agent.toml, or repository skills.[/]"
    )
    choice = Prompt.ask(
        "Trust project resources?",
        choices=["once", "always", "ignore"],
        default="ignore",
        console=console,
    )
    if choice == "always":
        manager.trust_always(workspace)
        return True
    return choice == "once"


def _approval_callback(console: Console) -> Callable[[ApprovalRequest], ApprovalDecision]:
    def decide(request: ApprovalRequest) -> ApprovalDecision:
        choice = Prompt.ask(
            f"Allow {request.action} for {request.subject}?",
            choices=["once", "session", "deny"],
            default="deny",
            console=console,
        )
        return {
            "once": ApprovalDecision.ALLOW_ONCE,
            "session": ApprovalDecision.ALLOW_SESSION,
            "deny": ApprovalDecision.DENY,
        }[choice]

    return decide


def _build_runtime(
    *,
    cwd: Path,
    model_name: str | None,
    permissions: str,
    interactive: bool,
    output: str,
    trust_project: bool,
    session_id: str | None = None,
) -> tuple[AgentController, RichRenderer | JsonlRenderer, ControllerFactory]:
    workspace = cwd.expanduser().resolve()
    data_dir = _data_dir()
    console = Console(
        no_color=bool(os.environ.get("NO_COLOR")),
        # JSONL records must remain one physical line. Rich output should wrap
        # at the terminal width instead of relying on terminal-side wrapping.
        soft_wrap=output == "jsonl",
    )
    trusted = _resolve_trust(
        workspace,
        data_dir,
        interactive=interactive,
        trust_project=trust_project,
        console=console,
    )
    overlay = {"model": {"name": model_name}} if model_name else None
    settings = load_settings(
        workspace,
        trusted_project=trusted,
        cli=overlay,
        data_dir=data_dir,
    )
    if not settings.model.api_key:
        raise ConfigError("OPENAI_API_KEY is not set")
    if output not in {"rich", "jsonl"}:
        raise ConfigError("--output must be rich or jsonl")
    if permissions not in {"prompt", "auto", "read-only"}:
        raise ConfigError("--permissions must be prompt, auto, or read-only")
    renderer: RichRenderer | JsonlRenderer
    if output == "jsonl":
        renderer = JsonlRenderer(console)
    else:
        renderer = RichRenderer(console=console, raw=settings.ui.raw_tool_output)
    approval = ApprovalPolicy(
        permissions,
        interactive=interactive,
        callback=_approval_callback(console) if interactive else None,
    )
    model = ModelClient(
        model=settings.model.name,
        api_key=settings.model.api_key,
        base_url=settings.model.base_url,
        max_retries=settings.model.max_retries,
    )
    sessions = SessionStore(settings.data_dir)
    memory = MemoryStore(
        data_dir=settings.data_dir,
        workspace=settings.cwd,
        enabled=settings.memory.enabled,
    )
    skills = SkillRegistry(workspace=settings.cwd)
    skills.discover(include_repo=trusted)
    instructions = load_agents_instructions(settings.cwd) if trusted else ""

    def factory(resume_id: str | None) -> AgentController:
        return AgentController(
            settings=settings,
            model=model,
            tools=default_registry(),
            sessions=sessions,
            memory=memory,
            skills=skills,
            approval=approval,
            agents_instructions=instructions,
            session_id=resume_id,
            event_sink=renderer.handle,
        )

    controller = factory(session_id)
    return controller, renderer, factory


def _report_cli_error(message: str, output: str = "rich") -> None:
    console = Console(stderr=True, color_system=None if output == "jsonl" else "auto")
    if output == "jsonl":
        console.print(json.dumps({"type": "error", "message": message}, ensure_ascii=False))
    else:
        console.print(f"[red]error:[/] {message}")


@app.callback()
def main(
    ctx: typer.Context,
    cwd: Annotated[Path, typer.Option("--cwd", help="Workspace directory.")] = Path("."),
    model: Annotated[
        str | None, typer.Option("--model", help="Override the configured model.")
    ] = None,
    permissions: Annotated[
        str, typer.Option("--permissions", help="prompt, auto, or read-only.")
    ] = "prompt",
    trust_project: Annotated[
        bool, typer.Option("--trust-project", help="Trust project resources once.")
    ] = False,
    version: Annotated[
        bool, typer.Option("--version", is_eager=True, help="Show version and exit.")
    ] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if ctx.invoked_subcommand is not None:
        return
    try:
        controller, renderer, factory = _build_runtime(
            cwd=cwd,
            model_name=model,
            permissions=permissions,
            interactive=True,
            output="rich",
            trust_project=trust_project,
        )
        if not isinstance(renderer, RichRenderer):
            raise ConfigError("interactive mode requires rich output")
        history = controller.settings.data_dir / "prompt-history.txt"
        history.parent.mkdir(parents=True, exist_ok=True)
        shell = InteractiveShell(
            controller=controller,
            controller_factory=factory,
            renderer=renderer,
            history_file=history,
        )
        raise typer.Exit(shell.run())
    except (ConfigError, SessionError, OSError, ValueError) as exc:
        _report_cli_error(str(exc))
        raise typer.Exit(2) from exc


@app.command("run")
def run_command(
    task: Annotated[str, typer.Argument(help="Task for the agent.")],
    cwd: Annotated[Path, typer.Option("--cwd", help="Workspace directory.")] = Path("."),
    output: Annotated[str, typer.Option("--output", help="rich or jsonl.")] = "rich",
    model: Annotated[str | None, typer.Option("--model")] = None,
    permissions: Annotated[str, typer.Option("--permissions")] = "prompt",
    trust_project: Annotated[bool, typer.Option("--trust-project")] = False,
) -> None:
    try:
        controller, renderer, _ = _build_runtime(
            cwd=cwd,
            model_name=model,
            permissions=permissions,
            interactive=False,
            output=output,
            trust_project=trust_project,
        )
        if isinstance(renderer, RichRenderer):
            renderer.header(
                model=controller.settings.model.name,
                cwd=controller.settings.cwd.name,
                permissions=permissions,
            )
        result = controller.run_turn(task)
        raise typer.Exit(result.exit_code)
    except (ConfigError, SessionError, OSError, ValueError) as exc:
        _report_cli_error(str(exc), output)
        raise typer.Exit(2) from exc


@app.command("resume")
def resume_command(
    session_id: Annotated[str, typer.Argument()],
    cwd: Annotated[Path, typer.Option("--cwd")] = Path("."),
    model: Annotated[str | None, typer.Option("--model")] = None,
    permissions: Annotated[str, typer.Option("--permissions")] = "prompt",
    trust_project: Annotated[bool, typer.Option("--trust-project")] = False,
) -> None:
    try:
        controller, renderer, factory = _build_runtime(
            cwd=cwd,
            model_name=model,
            permissions=permissions,
            interactive=True,
            output="rich",
            trust_project=trust_project,
            session_id=session_id,
        )
        if not isinstance(renderer, RichRenderer):
            raise ConfigError("interactive mode requires rich output")
        shell = InteractiveShell(
            controller=controller,
            controller_factory=factory,
            renderer=renderer,
            history_file=controller.settings.data_dir / "prompt-history.txt",
        )
        raise typer.Exit(shell.run())
    except (ConfigError, SessionError, OSError, ValueError) as exc:
        _report_cli_error(str(exc))
        raise typer.Exit(2) from exc


@app.command("sessions")
def sessions_command(
    output: Annotated[str, typer.Option("--output", help="table or json.")] = "table",
) -> None:
    if output not in {"table", "json"}:
        _report_cli_error("--output must be table or json")
        raise typer.Exit(2)
    sessions = SessionStore(_data_dir()).list()
    if output == "json":
        typer.echo(json.dumps(sessions, ensure_ascii=False, indent=2))
        return
    table = Table("Session", "Updated", "Title", "Records")
    for item in sessions:
        table.add_row(
            str(item["id"]),
            str(item["updated_at"]),
            str(item["title"]),
            str(item["records"]),
        )
    Console().print(table)
