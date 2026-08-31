from __future__ import annotations

import os
import re
import subprocess  # nosec B404
import tempfile
import time
from collections.abc import Callable
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
    rule_id: str | None = None
    risk_label: str | None = None
    matched_text: str | None = None
    guidance: str | None = None


@dataclass(frozen=True)
class CommandInvocation:
    executable: str
    args: tuple[str, ...]
    display: str


RuleMatcher = Callable[[CommandInvocation], str | None]


@dataclass(frozen=True)
class CommandSafetyRule:
    rule_id: str
    risk_label: str
    guidance: str
    matcher: RuleMatcher | None = None
    syntax_pattern: re.Pattern[str] | None = None

    def match(self, command: str, invocations: tuple[CommandInvocation, ...]) -> str | None:
        if self.syntax_pattern is not None and (match := self.syntax_pattern.search(command)):
            return match.group(0)
        if self.matcher is None:
            return None
        for invocation in invocations:
            if matched := self.matcher(invocation):
                return matched
        return None


_TOKEN_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s]+')
_NESTED_EXECUTORS = {
    "bash",
    "cmd",
    "dash",
    "eval",
    "find",
    "fish",
    "iex",
    "invoke-expression",
    "powershell",
    "pwsh",
    "sh",
    "xargs",
    "zsh",
}
_INFORMATIONAL_FLAGS = {"--help", "--version", "-h", "-?", "/?"}


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _command_name(value: str) -> str:
    normalized = _strip_quotes(value).replace("\\", "/").rsplit("/", 1)[-1].casefold()
    for suffix in (".exe", ".com", ".cmd", ".bat"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _split_shell_segments(command: str) -> tuple[str, ...]:
    """Split executable command segments without treating quoted text as shell syntax."""

    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    for character in command:
        if quote is not None:
            current.append(character)
            if escaped:
                escaped = False
            elif character == "\\" and quote == '"':
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
            current.append(character)
            continue
        if character in ";&|{}()":
            segment = "".join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            continue
        current.append(character)
    segment = "".join(current).strip()
    if segment:
        segments.append(segment)
    return tuple(segments)


def _tokens(segment: str) -> list[str]:
    return [_strip_quotes(token) for token in _TOKEN_PATTERN.findall(segment)]


def _unwrap_command(tokens: list[str]) -> list[str]:
    remaining = list(tokens)
    while remaining:
        name = _command_name(remaining[0])
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", remaining[0]):
            remaining.pop(0)
            continue
        if name in {"command", "nohup"}:
            remaining.pop(0)
            while remaining and remaining[0].startswith("-"):
                remaining.pop(0)
            continue
        if name in {"sudo", "doas"}:
            remaining.pop(0)
            while remaining and remaining[0].startswith("-"):
                option = remaining.pop(0).casefold()
                if option in {"-c", "-g", "-h", "-p", "-r", "-t", "-u"} and remaining:
                    remaining.pop(0)
            continue
        if name == "env":
            remaining.pop(0)
            while remaining and (
                remaining[0].startswith("-")
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", remaining[0]) is not None
            ):
                remaining.pop(0)
            continue
        break
    return remaining


def _nested_shell_payload(invocation: CommandInvocation) -> str | None:
    name = invocation.executable
    args = list(invocation.args)
    if name == "cmd":
        flags = {"/c", "/k"}
    elif name in {"powershell", "pwsh"}:
        flags = {"-c", "-command"}
    elif name in {"bash", "dash", "fish", "sh", "zsh"}:
        flags = {"-c"}
    elif name in {"eval", "iex", "invoke-expression"}:
        return " ".join(args) or None
    elif name == "find":
        for index, argument in enumerate(args):
            if argument.casefold() in {"-exec", "-execdir", "-ok", "-okdir"}:
                return " ".join(args[index + 1 :]) or None
        return None
    elif name == "xargs":
        index = 0
        options_with_values = {"-a", "-d", "-e", "-i", "-l", "-n", "-p", "-s"}
        while index < len(args) and args[index].startswith("-"):
            option = args[index].casefold()
            index += 1
            if option in options_with_values and index < len(args):
                index += 1
        return " ".join(args[index:]) or None
    else:
        return None
    for index, argument in enumerate(args):
        if argument.casefold() in flags and index + 1 < len(args):
            return " ".join(args[index + 1 :])
    return None


def _command_invocations(command: str, *, depth: int = 0) -> tuple[CommandInvocation, ...]:
    if depth > 4:
        return ()
    invocations: list[CommandInvocation] = []
    for segment in _split_shell_segments(command):
        tokens = _unwrap_command(_tokens(segment))
        if not tokens:
            continue
        invocation = CommandInvocation(
            executable=_command_name(tokens[0]),
            args=tuple(tokens[1:]),
            display=" ".join(tokens),
        )
        invocations.append(invocation)
        if invocation.executable in _NESTED_EXECUTORS:
            payload = _nested_shell_payload(invocation)
            if payload:
                invocations.extend(_command_invocations(payload, depth=depth + 1))
    return tuple(invocations)


def _git_action(invocation: CommandInvocation) -> tuple[str, tuple[str, ...]] | None:
    if invocation.executable != "git":
        return None
    args = list(invocation.args)
    index = 0
    options_with_values = {"-c", "-C", "--git-dir", "--work-tree", "--namespace"}
    while index < len(args):
        argument = args[index]
        if argument in options_with_values:
            index += 2
            continue
        if argument.startswith(("--git-dir=", "--work-tree=", "--namespace=")):
            index += 1
            continue
        if argument.startswith("-"):
            index += 1
            continue
        return argument.casefold(), tuple(args[index + 1 :])
    return None


def _git_reset_hard(invocation: CommandInvocation) -> str | None:
    action = _git_action(invocation)
    if action is None or action[0] != "reset":
        return None
    return "git reset --hard" if "--hard" in {arg.casefold() for arg in action[1]} else None


def _git_clean_force(invocation: CommandInvocation) -> str | None:
    action = _git_action(invocation)
    if action is None or action[0] != "clean":
        return None
    lowered = [arg.casefold() for arg in action[1]]
    if "--dry-run" in lowered or any(
        arg.startswith("-") and not arg.startswith("--") and "n" in arg[1:] for arg in lowered
    ):
        return None
    force = next(
        (
            arg
            for arg in action[1]
            if arg.casefold() == "--force"
            or (arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:].casefold())
        ),
        None,
    )
    return f"git clean {force}" if force else None


def _powershell_switch_enabled(arguments: list[str], switch: str) -> bool:
    """Return whether a PowerShell switch is present and not explicitly disabled."""

    normalized = switch.casefold().lstrip("-")
    for argument in arguments:
        candidate = argument.casefold().lstrip("-")
        name, separator, value = candidate.partition(":")
        if not normalized.startswith(name):
            continue
        return not (separator and value in {"$false", "false", "0"})
    return False


def _device_target(value: str) -> bool:
    normalized = value.strip("\"'").replace("\\", "/").casefold()
    if normalized.startswith("of="):
        normalized = normalized[3:]
    if normalized in {"/dev/null", "/dev/zero", "/dev/random", "/dev/urandom"}:
        return False
    return bool(
        normalized.startswith("/dev/")
        or normalized.startswith("//./physicaldrive")
        or normalized.startswith("//?/volume{")
        or re.fullmatch(r"[a-z]:", normalized)
    )


def _non_mutating_preview(arguments: list[str]) -> bool:
    lowered = [argument.casefold() for argument in arguments]
    return bool(
        {"--dry-run", "--no-act", "--noaction"}.intersection(lowered)
        or _powershell_switch_enabled(lowered, "whatif")
    )


def _recursive_delete(invocation: CommandInvocation) -> str | None:
    name = invocation.executable
    lowered = [arg.casefold() for arg in invocation.args]
    if _powershell_switch_enabled(lowered, "whatif") or all(
        arg in _INFORMATIONAL_FLAGS for arg in lowered
    ):
        return None
    if name in {"rm", "rmdir"} and any(
        arg == "--recursive"
        or (arg.startswith("-") and not arg.startswith("--") and "r" in arg[1:])
        for arg in lowered
    ):
        return invocation.display
    if name in {"del", "erase", "rd", "rmdir"} and "/s" in lowered:
        return invocation.display
    if name in {"remove-item", "ri"} and _powershell_switch_enabled(lowered, "recurse"):
        return invocation.display
    return None


def _disk_format(invocation: CommandInvocation) -> str | None:
    name = invocation.executable
    lowered = [arg.casefold() for arg in invocation.args]
    if _non_mutating_preview(lowered) or (
        lowered and all(arg in _INFORMATIONAL_FLAGS for arg in lowered)
    ):
        return None
    if name in {"diskpart", "format", "format-volume"}:
        return invocation.display
    if (name == "mkfs" or name.startswith("mkfs.")) and any(
        _device_target(argument) for argument in invocation.args
    ):
        return invocation.display
    return None


def _system_power(invocation: CommandInvocation) -> str | None:
    lowered = [argument.casefold() for argument in invocation.args]
    if _non_mutating_preview(lowered) or (
        lowered and all(argument in _INFORMATIONAL_FLAGS for argument in lowered)
    ):
        return None
    if invocation.executable == "shutdown" and {"/a", "-c", "--cancel"}.intersection(lowered):
        return None
    if invocation.executable in {
        "halt",
        "poweroff",
        "reboot",
        "restart-computer",
        "shutdown",
        "stop-computer",
    }:
        return invocation.display
    if invocation.executable in {"systemctl", "loginctl"} and any(
        argument.casefold() in {"halt", "hibernate", "hybrid-sleep", "poweroff", "reboot"}
        for argument in invocation.args
    ):
        return invocation.display
    if (
        invocation.executable in {"init", "telinit"}
        and invocation.args
        and invocation.args[0].casefold() in {"0", "6"}
    ):
        return invocation.display
    return None


def _direct_disk_write(invocation: CommandInvocation) -> str | None:
    lowered = [arg.casefold() for arg in invocation.args]
    if _non_mutating_preview(lowered) or (
        lowered and all(arg in _INFORMATIONAL_FLAGS for arg in lowered)
    ):
        return None
    if invocation.executable == "dd":
        return invocation.display if any(_device_target(arg) for arg in lowered) else None
    if invocation.executable in {"clear-disk", "initialize-disk"}:
        return invocation.display
    if invocation.executable in {"blkdiscard", "wipefs"} and any(
        _device_target(argument) for argument in lowered
    ):
        return invocation.display
    if invocation.executable in {"out-file", "set-content", "tee"} and any(
        _device_target(argument) for argument in lowered
    ):
        return invocation.display
    return None


def _encoded_shell_payload(invocation: CommandInvocation) -> str | None:
    if invocation.executable not in {"powershell", "pwsh"}:
        return None
    for argument in invocation.args:
        lowered = argument.casefold()
        if lowered in {"-e", "-ec", "-enc", "-encodedcommand"}:
            return invocation.display
    return None


class CommandPolicy:
    _forbidden = (
        CommandSafetyRule(
            "git-reset-hard",
            "破坏性 Git 重置",
            "先检查 git status 和 git diff，使用可保留工作区改动的恢复方式。",
            matcher=_git_reset_hard,
        ),
        CommandSafetyRule(
            "git-clean-force",
            "强制清理 Git 工作区",
            "先查看 git status 和 git clean -nd，再让用户确认精确目标。",
            matcher=_git_clean_force,
        ),
        CommandSafetyRule(
            "recursive-delete",
            "递归删除文件",
            "请限定到明确的工作区目标，并优先使用可恢复的删除方式。",
            matcher=_recursive_delete,
        ),
        CommandSafetyRule(
            "disk-format",
            "磁盘格式化操作",
            "此类操作可能破坏磁盘数据，请改用只读检查或在系统工具中人工处理。",
            matcher=_disk_format,
        ),
        CommandSafetyRule(
            "system-power",
            "系统电源操作",
            "请在 Agent 外部确认运行状态后，由用户直接执行电源操作。",
            matcher=_system_power,
        ),
        CommandSafetyRule(
            "direct-disk-write",
            "直接写入设备",
            "不要让 Agent 直接写入设备，请改用可审阅、可回滚的文件级操作。",
            matcher=_direct_disk_write,
        ),
        CommandSafetyRule(
            "encoded-shell-payload",
            "无法审查的编码脚本",
            "请让 Agent 使用可见的明文命令，确保安全规则和用户都能审阅实际操作。",
            matcher=_encoded_shell_payload,
        ),
        CommandSafetyRule(
            "fork-bomb",
            "进程耗尽攻击",
            "该命令会耗尽系统资源，必须移除。",
            syntax_pattern=re.compile(r":\(\)\s*\{\s*:\|:&\s*\}", re.IGNORECASE),
        ),
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
        invocations = _command_invocations(normalized)
        for rule in self._forbidden:
            if matched_text := rule.match(normalized, invocations):
                return CommandClassification(
                    False,
                    False,
                    "command matches a destructive safety rule",
                    rule_id=rule.rule_id,
                    risk_label=rule.risk_label,
                    matched_text=matched_text,
                    guidance=rule.guidance,
                )
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
    cancel_requested: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    timeout = min(max(timeout, 1), 300)
    if cancel_requested is not None and cancel_requested():
        return {
            "exit_code": 130,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "cancelled": True,
            "truncated": False,
        }
    creationflags: int
    if os.name == "nt":
        argv: str | list[str] = command
        shell = True
        executable = os.environ.get("COMSPEC", "cmd.exe")
        creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        start_new_session = False
    else:
        argv = ["/bin/sh", "-c", command]
        shell = False
        executable = None
        creationflags = 0
        start_new_session = True
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(  # nosec B602
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
        cancelled = False
        deadline = time.monotonic() + timeout
        try:
            while True:
                if cancel_requested is not None and cancel_requested():
                    cancelled = True
                    _terminate_tree(process)
                    exit_code = process.wait(timeout=3)
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    _terminate_tree(process)
                    exit_code = process.wait(timeout=3)
                    break
                try:
                    exit_code = process.wait(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            # Ctrl+C and interpreter shutdown must not leave the command or its children running.
            try:
                _terminate_tree(process)
                process.wait(timeout=3)
            except BaseException:
                pass
            raise
        out_text, out_truncated = _bounded_decode(stdout)
        err_text, err_truncated = _bounded_decode(stderr)
    return {
        "exit_code": exit_code,
        "stdout": out_text,
        "stderr": err_text,
        "timed_out": timed_out,
        "cancelled": cancelled,
        "truncated": out_truncated or err_truncated,
    }
