from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from coding_agent.events import ToolResult
from coding_agent.safety.approval import ApprovalRequest
from coding_agent.safety.paths import PathSafetyError
from coding_agent.tools.base import AppliedChange, Tool, ToolContext
from coding_agent.workspace_settings import VerificationCheck


class RegisterVerificationArgs(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["test", "build", "lint", "typecheck", "custom"] = "test"
    command: str = Field(min_length=1, max_length=20_000)
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    target_paths: list[str] = Field(default_factory=list, max_length=32)


class RunVerifyArgs(BaseModel):
    rule_id: str = Field(min_length=1, max_length=160)


def _is_within(path: str, target: str) -> bool:
    if target == ".":
        return True
    return path == target or path.startswith(target.rstrip("/") + "/")


def _created_artifacts(
    changes: list[AppliedChange],
    *,
    turn_id: str,
    target_paths: list[str],
) -> tuple[list[str], list[str]]:
    files: list[str] = []
    directories: list[str] = []
    for change in changes:
        if change.turn_id != turn_id or change.kind != "created":
            continue
        if not any(_is_within(change.path, target) for target in target_paths):
            continue
        if change.path not in files:
            files.append(change.path)
        for directory in change.created_directories:
            if directory not in directories:
                directories.append(directory)
    return files, directories


class RegisterVerificationTool(Tool):
    name = "register_verification"
    description = (
        "Register or update a deterministic project verification rule. Use this after creating "
        "or discovering a self-contained subproject so verification runs from the correct "
        "workspace-relative directory. The command still uses normal safety checks and approval."
    )
    args_model = RegisterVerificationArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = RegisterVerificationArgs.model_validate(args)
        try:
            root = context.workspace.resolve(values.cwd, must_exist=True)
        except PathSafetyError as exc:
            return ToolResult(
                ok=False,
                code="INVALID_VERIFICATION_ROOT",
                summary=f"verification working directory does not exist or is unsafe: {exc}",
            )
        if not root.is_dir():
            return ToolResult(
                ok=False,
                code="INVALID_VERIFICATION_ROOT",
                summary="verification working directory is not a directory",
            )
        cwd = context.workspace.display(root) or "."
        raw_targets = values.target_paths or [cwd]
        targets: list[str] = []
        try:
            for raw_target in raw_targets:
                resolved = context.workspace.resolve(raw_target, must_exist=True)
                display = context.workspace.display(resolved) or "."
                if display not in targets:
                    targets.append(display)
        except PathSafetyError as exc:
            return ToolResult(
                ok=False,
                code="INVALID_VERIFICATION_TARGET",
                summary=f"verification target does not exist or is unsafe: {exc}",
            )

        digest = hashlib.sha256(f"{cwd}\0{values.command.strip()}".encode()).hexdigest()[:16]
        try:
            check = VerificationCheck(
                id=f"agent-{digest}",
                label=values.label,
                kind=values.kind,
                command=values.command,
                cwd=cwd,
                timeout_seconds=values.timeout_seconds,
                enabled=True,
                source="agent",
                target_paths=targets,
            )
        except ValueError as exc:
            return ToolResult(
                ok=False,
                code="INVALID_VERIFICATION_RULE",
                summary=str(exc),
            )

        diff = (
            f"Verification rule: {check.label}\n"
            f"Command: {check.command}\n"
            f"Working directory: {check.cwd}\n"
            f"Applies to: {', '.join(check.target_paths)}\n"
            f"Timeout: {check.timeout_seconds}s\n"
        )
        if not context.approve(
            ApprovalRequest(
                action="register_verification",
                subject=f"{check.cwd}: {check.command}",
                summary=f"register verification: {check.label}",
                diff=diff,
            )
        ):
            return ToolResult(
                ok=False,
                code="APPROVAL_DENIED",
                summary="verification registration was denied",
            )
        try:
            registered = context.register_verification(check)
        except ValueError as exc:
            return ToolResult(
                ok=False,
                code="REGISTRATION_UNAVAILABLE",
                summary=str(exc),
            )
        created_files, created_directories = _created_artifacts(
            context.working.changes,
            turn_id=context.turn_id,
            target_paths=registered.target_paths or [registered.cwd],
        )
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"registered {registered.label} in {registered.cwd}",
            data={
                "verification_check": registered.model_dump(mode="json"),
                "created_files": created_files,
                "created_directories": created_directories,
            },
        )


class RunVerifyTool(Tool):
    name = "run_verify"
    description = (
        "Run one registered verification rule by id. This is the only Agent-facing way to run "
        "tests, builds, linters, or type checks as verification evidence. It delegates to the "
        "ordinary run_command implementation, preserving workspace confinement, hard safety "
        "rules, approval, timeout, cancellation, and structured GUI verification status."
    )
    args_model = RunVerifyArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = RunVerifyArgs.model_validate(args)
        try:
            return context.run_verification(values.rule_id)
        except ValueError as exc:
            return ToolResult(
                ok=False,
                code="VERIFICATION_UNAVAILABLE",
                summary=str(exc),
            )
