from __future__ import annotations

import socket
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from typing import cast

import uvicorn

from coding_agent.branding import PRODUCT_NAME
from coding_agent.config import ConfigError
from coding_agent.controller import AgentController
from coding_agent.runtime import RuntimeFactory
from coding_agent.runtime_management import RuntimeManagement
from coding_agent.web.app import create_web_app
from coding_agent.web.approval import ApprovalBroker
from coding_agent.web.auth import LaunchAuth
from coding_agent.web.coordinator import TurnCoordinator
from coding_agent.web.handshake import DesktopHandshake, serialize_desktop_handshake
from coding_agent.workspace_settings import WorkspaceSettingsStore


def _loopback_listener() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    return listener


def _open_when_ready(
    server: uvicorn.Server,
    url: str,
    browser_open: Callable[[str], bool],
) -> None:
    for _ in range(400):
        if server.started:
            browser_open(url)
            return
        if server.should_exit:
            return
        time.sleep(0.025)


def launch_web(
    *,
    workspace: Path,
    data_dir: Path,
    model_name: str | None,
    permissions: str,
    trusted_project: bool,
    open_browser: bool,
    static_dir: Path | None = None,
    browser_open: Callable[[str], bool] = webbrowser.open,
    desktop_handshake: Callable[[str], None] | None = None,
) -> int:
    assets = static_dir or Path(__file__).with_name("static")
    if not (assets / "index.html").is_file():
        raise ConfigError("Web UI assets are not built; run npm install and npm run build in web/")

    listener = _loopback_listener()
    port = int(listener.getsockname()[1])
    host = f"127.0.0.1:{port}"
    origin = f"http://{host}"
    auth = LaunchAuth(host=host, origin=origin)
    coordinator = TurnCoordinator()
    broker = ApprovalBroker(on_request=coordinator.publish_approval)
    coordinator.attach_approval_broker(broker)
    runtime = RuntimeFactory(
        workspace=workspace,
        data_dir=data_dir,
        permissions=permissions,
        trusted_project=trusted_project,
        interactive=True,
        model_name=model_name,
        event_sink=coordinator.handle_agent_event,
        approval_callback=broker.request,
    )
    coordinator.attach_runtime(runtime)
    coordinator.attach_management(
        RuntimeManagement(
            runtime=runtime,
            controller_provider=cast(Callable[[], AgentController], coordinator.controller),
            workspace_settings=WorkspaceSettingsStore(
                data_dir=runtime.settings.data_dir,
                workspace=runtime.settings.cwd,
            ),
        )
    )
    coordinator.configure_workspace_services(
        workspace=runtime.settings.cwd,
        sessions=runtime.sessions,
    )
    coordinator.configure_runtime_metadata(
        workspace_name=runtime.settings.cwd.name or str(runtime.settings.cwd),
        workspace_path=str(runtime.settings.cwd),
        model=runtime.settings.model.name,
        permissions=runtime.permissions,
        context_window=runtime.settings.agent.context_window,
    )
    app = create_web_app(coordinator=coordinator, auth=auth, static_dir=assets)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    url = f"{origin}/#capability={auth.capability}"
    if desktop_handshake is None:
        print(f"{PRODUCT_NAME} Web UI: {url}")
    else:
        desktop_handshake(
            serialize_desktop_handshake(DesktopHandshake(origin=origin, capability=auth.capability))
        )
    if open_browser:
        Thread(
            target=_open_when_ready,
            args=(server, url, browser_open),
            name="forge-web-browser",
            daemon=True,
        ).start()
    try:
        server.run(sockets=[listener])
    finally:
        coordinator.disconnect()
        broker.close()
        auth.revoke()
        listener.close()
    return 0
