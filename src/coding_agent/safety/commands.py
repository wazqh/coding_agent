from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil


MAX_CAPTURE_BYTES = 32 * 1024
SECRET_NAME = re.compile(r"(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)


@dataclass(frozen=True)
class CommandClassification:
    allowed: bool
    approval_required: bool
    reason: str


class CommandPolicy:
    _forbidden = (
        re.compile(r"\bgit\s+reset\b[^\r\n]*--hard", re.IGNORECASE),
        re.compile(r"\bgit\s+clean\b[^\r\n]*(?:-\w*f\w*|--force)", re.IGNORECASE),
        re.compile(r"\b(?:rm|rmdir)\b[^\r\n]*(?:-[^\s]*r|--recursive)", re.IGNORECASE),
        re.compile(r"\bremove-item\b[^\r\n]*-recurse", re.IGNORECASE),
        re.compile(r"\b(?:del|rd)\b[^\r\n]*/s", re.IGNORECASE),
        re.compile(r"\b(?:mkfs(?:\.\w+)?|diskpart|format)\b", re.IGNORECASE),
        re.compile(r"\b(?:shutdown|reboot|halt|poweroff|stop-computer|restart-computer)\b", re.IGNORECASE),
        re.compile(r"\bdd\s+[^\r\n]*\bof=", re.IGNORECASE),
        re.compile(r":\(\)\s*\{\s*:\|:&\s*\}", re.IGNORECASE),
    )
    _read_only = (
        re.compile(r"^(?:pwd|ls|dir|tree|rg|grep|findstr|where|which)(?:\s|$)", re.IGNORECASE),
        re.compile(r"^(?:get-location|get-childitem|get-content)(?:\s|$)", re.IGNORECASE),
        re.compile(r"^git\s+(?:status|diff|log|show|branch|rev-parse)(?:\s|$)", re.IGNORECASE),
        re.compile(r"^(?:python|python3|node|npm|git)\s+--version(?:\s|$)", re.IGNORECASE),
    )

    def classify(self, command: str) -> CommandClassification:
        normalized = command.strip()
        if not normalized or "\x00" in normalized or "\n" in normalized or "\r" in normalized:
            return CommandClassification(False, False, "empty, NUL, or multiline command")
        for pattern in self._forbidden:
            if pattern.search(normalized):
                return CommandClassification(False, False, "command matches a destructive safety rule")
        has_operators = bool(re.search(r"[;&|<>`]", normalized))
        if not has_operators and any(pattern.match(normalized) for pattern in self._read_only):
            return CommandClassification(True, False, "read-only allowlist")
        return CommandClassification(True, True, "command requires approval")


def sanitized_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    values = dict(os.environ if source is None else source)
    return {name: value for name, value in values.items() if not SECRET_NAME.search(name)}


def _terminate_tree(process: subprocess.Popen[bytes]) -> None:
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in children:
            child.terminate()
        _, alive = psutil.wait_procs(children, timeout=1.5)
        for child in alive:
            child.kill()
        parent.terminate()
        try:
            parent.wait(timeout=1.5)
        except psutil.TimeoutExpired:
            parent.kill()
    except psutil.Error:
        process.kill()


def _bounded_decode(stream: Any, limit: int = MAX_CAPTURE_BYTES) -> tuple[str, bool]:
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size <= limit:
        return stream.read().decode("utf-8", errors="replace"), False
    half = limit // 2
    head = stream.read(half)
    stream.seek(-half, os.SEEK_END)
    tail = stream.read(half)
    marker = b"\n... output truncated ...\n"
    return (head + marker + tail).decode("utf-8", errors="replace"), True


def run_subprocess(
    command: str,
    *,
    cwd: Path,
    timeout: int,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    timeout = min(max(timeout, 1), 300)
    creationflags: int
    if os.name == "nt":
        argv: str | list[str] = command
        shell = True
        executable = os.environ.get("COMSPEC", "cmd.exe")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        start_new_session = False
    else:
        argv = ["/bin/sh", "-c", command]
        shell = False
        executable = None
        creationflags = 0
        start_new_session = True
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(  # noqa: S603  # nosec B602 - screened and approved
            argv,
            shell=shell,
            executable=executable,
            cwd=cwd,
            env=sanitized_environment(environ),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_tree(process)
            exit_code = process.wait(timeout=3)
        out_text, out_truncated = _bounded_decode(stdout)
        err_text, err_truncated = _bounded_decode(stderr)
    return {
        "exit_code": exit_code,
        "stdout": out_text,
        "stderr": err_text,
        "timed_out": timed_out,
        "truncated": out_truncated or err_truncated,
    }
