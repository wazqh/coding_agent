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
from rich.text import Text

from coding_agent import __version__
from coding_agent.branding import COMMAND_NAME, PRODUCT_NAME
from coding_agent.config import ConfigError
from coding_agent.controller import AgentController
from coding_agent.credentials import (
    CredentialService,
    KeyringCredentialService,
    MemoryCredentialService,
    provider_credential_ref,
)
from coding_agent.model_catalog import ModelCatalog, ModelSelectionStore
from coding_agent.project import TrustManager
from coding_agent.runtime import RuntimeFactory
from coding_agent.safety.approval import ApprovalDecision, ApprovalRequest
from coding_agent.session import SessionError, SessionStore
from coding_agent.ui.prompt import ControllerFactory, InteractiveShell
from coding_agent.ui.render import JsonlRenderer, RichRenderer
from coding_agent.workspace_settings import WorkspaceSettingsStore

app = typer.Typer(
    name=COMMAND_NAME,
    help=f"{PRODUCT_NAME}: a safe, local-first CLI coding agent.",
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


def _approval_callback(
    console: Console,
    renderer: RichRenderer | None = None,
) -> Callable[[ApprovalRequest], ApprovalDecision]:
    def decide(request: ApprovalRequest) -> ApprovalDecision:
        paused = renderer.pause_turn_status() if renderer is not None else False
        try:
            console.print()
            console.print("  [bold]Choose an approval:[/]")
            console.print("    [cyan]1[/]  Allow this operation once")
            console.print("    [cyan]2[/]  Allow matching operations for this session")
            console.print("    [red]3[/]  Deny and return the result to the agent")
            choice = Prompt.ask(
                "  Selection",
                choices=["1", "2", "3"],
                default="3",
                console=console,
            )
            console.print()
        finally:
            if paused and renderer is not None:
                renderer.resume_turn_status()
        return {
            "1": ApprovalDecision.ALLOW_ONCE,
            "2": ApprovalDecision.ALLOW_SESSION,
            "3": ApprovalDecision.DENY,
            "once": ApprovalDecision.ALLOW_ONCE,
            "session": ApprovalDecision.ALLOW_SESSION,
            "deny": ApprovalDecision.DENY,
        }[choice]

    return decide


def _prepare_credentials(
    *,
    data_dir: Path,
    interactive: bool,
    console: Console,
) -> CredentialService:
    system_credentials = KeyringCredentialService()
    credentials: CredentialService = (
        system_credentials if system_credentials.available else MemoryCredentialService()
    )
    if not interactive:
        return credentials
    catalog = ModelCatalog(
        path=data_dir / "models.toml", environ=os.environ, credentials=credentials
    )
    if not catalog.providers():
        return credentials
    active = ModelSelectionStore(data_dir=data_dir).load()
    provider = (
        active.provider
        if active is not None and active.provider in catalog.providers()
        else catalog.default_provider or catalog.providers()[0]
    )
    profile = catalog.config.providers[provider]
    reference = profile.credential_ref or provider_credential_ref(provider)
    if os.environ.get(profile.api_key_env) or credentials.get(reference):
        return credentials
    console.print(f"[yellow]API Key required for provider {provider!r}.[/]")
    api_key = Prompt.ask("API Key", password=True, console=console).strip()
    credentials.set(reference, api_key)
    if not credentials.persistent:
        console.print(
            "[yellow]Secure system storage is unavailable; "
            "the key will be kept only for this process.[/]"
        )
    return credentials


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
    if output not in {"rich", "jsonl"}:
        raise ConfigError("--output must be rich or jsonl")
    renderer: RichRenderer | JsonlRenderer = (
        JsonlRenderer(console) if output == "jsonl" else RichRenderer(console=console)
    )
    credentials = _prepare_credentials(
        data_dir=data_dir,
        interactive=interactive,
        console=console,
    )
    runtime = RuntimeFactory(
        workspace=workspace,
        data_dir=data_dir,
        permissions=permissions,
        trusted_project=trusted,
        interactive=interactive,
        model_name=model_name,
        event_sink=renderer.handle,
        approval_callback=(
            _approval_callback(console, renderer if isinstance(renderer, RichRenderer) else None)
            if interactive
            else None
        ),
        credentials=credentials,
    )
    if isinstance(renderer, RichRenderer):
        renderer.raw = runtime.settings.ui.raw_tool_output
    controller = runtime.create(session_id)
    return controller, renderer, runtime.controller_factory()


def _report_cli_error(message: str, output: str = "rich") -> None:
    console = Console(stderr=True, color_system=None if output == "jsonl" else "auto")
    if output == "jsonl":
        console.print(json.dumps({"type": "error", "message": message}, ensure_ascii=False))
    else:
        line = Text("error: ", style="red")
        line.append(message)
        console.print(line)


def _load_web_launcher() -> Callable[..., int]:
    from coding_agent.web.launcher import launch_web

    return launch_web


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
            workspace_settings=WorkspaceSettingsStore(
                data_dir=controller.settings.data_dir,
                workspace=controller.settings.cwd,
            ),
            configured_max_steps=getattr(
                getattr(controller.settings, "agent", None), "configured_max_steps", 24
            ),
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


@app.command("web")
def web_command(
    cwd: Annotated[Path, typer.Option("--cwd", help="Workspace directory.")] = Path("."),
    model: Annotated[str | None, typer.Option("--model")] = None,
    permissions: Annotated[str, typer.Option("--permissions")] = "prompt",
    trust_project: Annotated[bool, typer.Option("--trust-project")] = False,
    no_open: Annotated[
        bool, typer.Option("--no-open", help="Do not open the browser automatically.")
    ] = False,
    desktop_handshake: Annotated[
        bool,
        typer.Option("--desktop-handshake", hidden=True),
    ] = False,
    desktop_trust: Annotated[
        str | None,
        typer.Option("--desktop-trust", hidden=True),
    ] = None,
) -> None:
    try:
        workspace = cwd.expanduser().resolve()
        data_dir = _data_dir()
        if desktop_handshake:
            if desktop_trust not in {None, "once", "always", "ignore"}:
                raise ValueError("Invalid desktop project trust choice")
            manager = TrustManager(data_dir)
            status = manager.status(workspace)
            if desktop_trust is None and status.has_resources and not status.trusted:
                payload = json.dumps(
                    {"workspace": str(workspace)},
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                typer.echo(f"FORGE_DESKTOP_TRUST_REQUIRED {payload}")
                raise typer.Exit(3)
            if desktop_trust == "always":
                manager.trust_always(workspace)
            trust_project = desktop_trust in {"once", "always"}
        try:
            launcher = _load_web_launcher()
        except ModuleNotFoundError as exc:
            _report_cli_error('Web UI dependencies are not installed; run pip install -e ".[web]"')
            raise typer.Exit(2) from exc
        trusted = _resolve_trust(
            workspace,
            data_dir,
            interactive=not desktop_handshake,
            trust_project=trust_project,
            console=Console(no_color=bool(os.environ.get("NO_COLOR"))),
        )
        exit_code = launcher(
            workspace=workspace,
            data_dir=data_dir,
            model_name=model,
            permissions=permissions,
            trusted_project=trusted,
            open_browser=not no_open,
            desktop_handshake=typer.echo if desktop_handshake else None,
        )
        raise typer.Exit(exit_code)
    except (ConfigError, SessionError, OSError, ValueError) as exc:
        _report_cli_error(str(exc))
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
            workspace_settings=WorkspaceSettingsStore(
                data_dir=controller.settings.data_dir,
                workspace=controller.settings.cwd,
            ),
            configured_max_steps=getattr(
                getattr(controller.settings, "agent", None), "configured_max_steps", 24
            ),
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
