from __future__ import annotations

from pydantic import BaseModel, Field

from coding_agent.events import ToolResult
from coding_agent.safety.approval import ApprovalRequest
from coding_agent.safety.commands import CommandPolicy, run_subprocess
from coding_agent.tools.base import Tool, ToolContext


class RunCommandArgs(BaseModel):
    command: str = Field(min_length=1, max_length=20_000)
    timeout: int | None = Field(default=None, ge=1, le=300)


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
                data={"command": values.command, "hard_blocked": True},
            )
        if classification.approval_required and not context.approve(
            ApprovalRequest(
                action="run_command",
                subject=values.command,
                summary=f"run command: {values.command}",
            )
        ):
            return ToolResult(ok=False, code="APPROVAL_DENIED", summary="command was denied")
        timeout = values.timeout or context.command_timeout
        result = run_subprocess(
            values.command,
            cwd=context.workspace.root,
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
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            },
            retryable=bool(result["timed_out"]),
            truncated=bool(result["truncated"]),
        )
