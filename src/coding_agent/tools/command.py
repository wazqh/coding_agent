from __future__ import annotations

from pydantic import BaseModel, Field

from coding_agent.events import ToolResult
from coding_agent.safety.approval import ApprovalRequest
from coding_agent.safety.commands import CommandPolicy, run_subprocess
from coding_agent.safety.paths import PathSafetyError
from coding_agent.tools.base import Tool, ToolContext


class RunCommandArgs(BaseModel):
    command: str = Field(min_length=1, max_length=20_000)
    cwd: str = Field(default=".", min_length=1, max_length=4096)
    timeout: int | None = Field(default=None, ge=1, le=3600)


class RunCommandTool(Tool):
    name = "run_command"
    description = (
        "Run a command in the workspace with danger screening, approval, timeout, "
        "and bounded output."
    )
    args_model = RunCommandArgs

    def __init__(self, policy: CommandPolicy | None = None) -> None:
        self.policy = policy or CommandPolicy()

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = RunCommandArgs.model_validate(args)
        classification = self.policy.classify(values.command)
        if not classification.allowed:
            return ToolResult(
                ok=False,
                code="DANGEROUS_COMMAND",
                summary=classification.reason,
                data={
                    "command": values.command,
                    "cwd": values.cwd,
                    "hard_blocked": True,
                    "rule_id": classification.rule_id,
                    "risk_label": classification.risk_label,
                    "matched_text": classification.matched_text,
                    "guidance": classification.guidance,
                },
            )
        command_cwd = context.workspace.resolve(values.cwd)
        if not command_cwd.is_dir():
            raise PathSafetyError(f"command cwd is not a directory: {values.cwd}")
        relative_cwd = context.workspace.display(command_cwd)
        if (
            classification.approval_required
            and not context.is_verification_command_authorized(values.command, relative_cwd)
            and not context.approve(
                ApprovalRequest(
                    action="run_command",
                    subject=values.command,
                    summary=f"run command in {relative_cwd}: {values.command}",
                )
            )
        ):
            return ToolResult(
                ok=False,
                code="APPROVAL_DENIED",
                summary="command was denied",
                data={"command": values.command, "cwd": relative_cwd},
            )
        timeout = values.timeout or context.command_timeout
        result = run_subprocess(
            values.command,
            cwd=command_cwd,
            timeout=timeout,
            cancel_requested=context.cancel_requested,
        )
        ok = result["exit_code"] == 0 and not result["timed_out"] and not result["cancelled"]
        if result["cancelled"]:
            code = "CANCELLED"
            summary = "command cancelled by user"
        elif result["timed_out"]:
            code = "TIMEOUT"
            summary = f"command timed out after {timeout}s"
        else:
            code = "OK" if ok else "COMMAND_FAILED"
            summary = f"command exited with code {result['exit_code']}"
        return ToolResult(
            ok=ok,
            code=code,
            summary=summary,
            data={
                "command": values.command,
                "cwd": relative_cwd,
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            },
            retryable=bool(result["timed_out"]),
            truncated=bool(result["truncated"]),
        )
