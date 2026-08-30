from __future__ import annotations

import difflib
import re
from contextlib import suppress
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from coding_agent.events import ToolResult
from coding_agent.safety.approval import ApprovalRequest
from coding_agent.safety.paths import WorkspacePaths, atomic_write_text, sha256_file, sha256_text
from coding_agent.tools.base import AppliedChange, Tool, ToolContext, WorkingState

MAX_TEXT_CHARS = 2 * 1024 * 1024
MAX_DIFF_CHARS = 32 * 1024
MAX_CHANGE_HISTORY = 100
MAX_UNDO_BACKUP_CHARS = 8 * 1024 * 1024


def _read_text(path: Path) -> str:
    if path.stat().st_size > MAX_TEXT_CHARS * 4:
        raise ValueError("file is too large")
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            content = stream.read(MAX_TEXT_CHARS + 1)
    except UnicodeDecodeError as exc:
        raise ValueError("file is not valid UTF-8 text") from exc
    if len(content) > MAX_TEXT_CHARS:
        raise ValueError("file is too large")
    return content


def _diff(path: str, before: str, after: str) -> tuple[str, bool]:
    value = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    if len(value) <= MAX_DIFF_CHARS:
        return value, False
    half = MAX_DIFF_CHARS // 2
    return value[:half] + "\n... diff truncated ...\n" + value[-half:], True


def _record_change(
    context: ToolContext,
    *,
    path: str,
    kind: Literal["created", "modified"],
    before_text: str | None,
    after_sha256: str,
    diff: str,
    reversible: bool,
) -> AppliedChange:
    change = AppliedChange(
        path=path,
        kind=kind,
        before_text=before_text,
        after_sha256=after_sha256,
        diff=diff,
        reversible=reversible,
    )
    context.working.changes.append(change)
    context.working.diffs.append(diff)
    while len(context.working.changes) > MAX_CHANGE_HISTORY:
        expired = context.working.changes.pop(0)
        with suppress(ValueError):
            context.working.diffs.remove(expired.diff)
    backup_chars = sum(len(item.before_text or "") for item in context.working.changes)
    if backup_chars > MAX_UNDO_BACKUP_CHARS:
        for item in context.working.changes:
            if backup_chars <= MAX_UNDO_BACKUP_CHARS:
                break
            if item.before_text is None:
                continue
            backup_chars -= len(item.before_text)
            item.before_text = None
            item.reversible = False
    return change


def undo_change(
    working: WorkingState,
    workspace: WorkspacePaths,
    change_id: str,
) -> AppliedChange:
    """Undo one recorded Diff only when the workspace still matches its after-state."""

    change = next((item for item in working.changes if item.id == change_id), None)
    if change is None:
        raise ValueError("this Diff is no longer available")
    if not change.reversible:
        raise ValueError("this Diff was truncated and cannot be safely undone")
    path = workspace.resolve(change.path, must_exist=True, file_only=True)
    if sha256_file(path) != change.after_sha256:
        raise ValueError("file changed since this Diff was recorded")
    if change.kind == "created":
        path.unlink()
    else:
        atomic_write_text(path, change.before_text or "")

    working.changes = [item for item in working.changes if item.id != change.id]
    with suppress(ValueError):
        working.diffs.remove(change.diff)
    latest = next(
        (item for item in reversed(working.changes) if item.path == change.path),
        None,
    )
    if latest is None:
        working.modified_files.pop(change.path, None)
    else:
        working.modified_files[change.path] = latest.after_sha256
    return change


class ListFilesArgs(BaseModel):
    path: str = "."
    pattern: str = "**/*"
    max_results: int = Field(default=200, ge=1, le=1000)


class ListFilesTool(Tool):
    name = "list_files"
    description = (
        "List workspace files under a relative directory. Never reads outside the workspace."
    )
    args_model = ListFilesArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = ListFilesArgs.model_validate(args)
        root = context.workspace.resolve(values.path, must_exist=True)
        if not root.is_dir():
            return ToolResult(ok=False, code="NOT_DIRECTORY", summary="path is not a directory")
        entries: list[dict[str, str | int]] = []
        for path in root.glob(values.pattern):
            if ".git" in path.parts or not context.workspace.contains(path):
                continue
            try:
                relative = context.workspace.display(path)
                kind = "dir" if path.is_dir() else "file"
                size = 0 if path.is_dir() else path.stat().st_size
            except OSError:
                continue
            entries.append({"path": relative, "type": kind, "size": size})
            if len(entries) >= values.max_results:
                break
        entries.sort(key=lambda item: str(item["path"]))
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"listed {len(entries)} entries under {values.path}",
            data={"entries": entries},
            truncated=len(entries) == values.max_results,
        )


class ReadFileArgs(BaseModel):
    path: str
    start_line: int = Field(default=1, ge=1)
    line_count: int = Field(default=400, ge=1, le=2000)


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 workspace file with line bounds and return its SHA-256."
    args_model = ReadFileArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = ReadFileArgs.model_validate(args)
        path = context.workspace.resolve(values.path, must_exist=True, file_only=True)
        content = _read_text(path)
        lines = content.splitlines(keepends=True)
        start = values.start_line - 1
        selected = "".join(lines[start : start + values.line_count])
        selected_count = len(lines[start : start + values.line_count])
        end_line = values.start_line + selected_count - 1 if selected_count else values.start_line
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"read {values.path} lines {values.start_line}-{end_line}",
            data={
                "path": values.path,
                "content": selected,
                "sha256": sha256_file(path),
                "total_lines": len(lines),
            },
            truncated=start + values.line_count < len(lines),
        )


class SearchTextArgs(BaseModel):
    pattern: str = Field(min_length=1, max_length=500)
    path: str = "."
    glob: str = "**/*"
    regex: bool = False
    case_sensitive: bool = False
    max_results: int = Field(default=100, ge=1, le=500)


class SearchTextTool(Tool):
    name = "search_text"
    description = "Search UTF-8 workspace files and return matching paths, lines, and snippets."
    args_model = SearchTextArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = SearchTextArgs.model_validate(args)
        root = context.workspace.resolve(values.path, must_exist=True)
        flags = 0 if values.case_sensitive else re.IGNORECASE
        expression = values.pattern if values.regex else re.escape(values.pattern)
        try:
            compiled = re.compile(expression, flags)
        except re.error as exc:
            return ToolResult(ok=False, code="INVALID_PATTERN", summary=str(exc))
        matches: list[dict[str, str | int]] = []
        candidates = [root] if root.is_file() else root.glob(values.glob)
        for path in candidates:
            if not path.is_file() or ".git" in path.parts or not context.workspace.contains(path):
                continue
            try:
                if path.stat().st_size > MAX_TEXT_CHARS * 4:
                    continue
                with path.open("r", encoding="utf-8", errors="strict") as stream:
                    for line_number, line in enumerate(stream, 1):
                        if compiled.search(line):
                            matches.append(
                                {
                                    "path": context.workspace.display(path),
                                    "line": line_number,
                                    "text": line.rstrip()[:500],
                                }
                            )
                            if len(matches) >= values.max_results:
                                break
            except (OSError, UnicodeError):
                continue
            if len(matches) >= values.max_results:
                break
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"found {len(matches)} matches for {values.pattern!r}",
            data={"matches": matches},
            truncated=len(matches) == values.max_results,
        )


class EditFileArgs(BaseModel):
    path: str
    old_text: str = Field(min_length=1)
    new_text: str
    expected_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace one unique text occurrence after SHA-256 validation and approval."
    args_model = EditFileArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = EditFileArgs.model_validate(args)
        path = context.workspace.resolve(values.path, must_exist=True, file_only=True)
        before = _read_text(path)
        actual_hash = sha256_text(before)
        if actual_hash != values.expected_sha256.lower():
            return ToolResult(
                ok=False,
                code="HASH_CONFLICT",
                summary="file changed since it was read",
                data={"actual_sha256": actual_hash},
                retryable=True,
            )
        occurrences = before.count(values.old_text)
        if occurrences != 1:
            return ToolResult(
                ok=False,
                code="NON_UNIQUE_MATCH",
                summary=f"old_text must match exactly once; found {occurrences}",
            )
        after = before.replace(values.old_text, values.new_text, 1)
        patch, truncated = _diff(values.path, before, after)
        if not context.approve(
            ApprovalRequest(
                action="edit_file",
                subject=values.path,
                summary=f"edit {values.path}",
                diff=patch,
            )
        ):
            return ToolResult(ok=False, code="APPROVAL_DENIED", summary="file edit was denied")
        current_path = context.workspace.resolve(values.path, must_exist=True, file_only=True)
        if current_path != path:
            return ToolResult(
                ok=False,
                code="PATH_CONFLICT",
                summary="file path changed while approval was pending",
                retryable=True,
            )
        if sha256_file(current_path) != actual_hash:
            return ToolResult(
                ok=False,
                code="HASH_CONFLICT",
                summary="file changed while approval was pending",
                retryable=True,
            )
        atomic_write_text(path, after)
        new_hash = sha256_text(after)
        context.working.modified_files[values.path] = new_hash
        change = _record_change(
            context,
            path=values.path,
            kind="modified",
            before_text=before,
            after_sha256=new_hash,
            diff=patch,
            reversible=not truncated,
        )
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"updated {values.path}",
            data={
                "path": values.path,
                "sha256": new_hash,
                "diff": patch,
                "change_id": change.id,
                "change_kind": change.kind,
                "reversible": change.reversible,
            },
            truncated=truncated,
        )


class WriteFileArgs(BaseModel):
    path: str
    content: str
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


class WriteFileTool(Tool):
    name = "write_file"
    description = (
        "Create or overwrite a UTF-8 file atomically; overwrites require expected SHA-256."
    )
    args_model = WriteFileArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = WriteFileArgs.model_validate(args)
        if len(values.content) > MAX_TEXT_CHARS:
            return ToolResult(ok=False, code="TOO_LARGE", summary="content exceeds 2 MiB")
        path = context.workspace.resolve(values.path, must_exist=False, file_only=True)
        exists = path.exists()
        before = _read_text(path) if exists else ""
        actual_hash = sha256_text(before) if exists else None
        expected_hash = values.expected_sha256
        if exists and expected_hash is None:
            return ToolResult(
                ok=False,
                code="HASH_REQUIRED",
                summary="expected_sha256 is required when overwriting a file",
            )
        if exists and expected_hash is not None and actual_hash != expected_hash.lower():
            return ToolResult(
                ok=False,
                code="HASH_CONFLICT",
                summary="file changed since it was read",
                data={"actual_sha256": actual_hash},
                retryable=True,
            )
        patch, truncated = _diff(values.path, before, values.content)
        action = "overwrite" if exists else "create"
        if not context.approve(
            ApprovalRequest(
                action="write_file",
                subject=values.path,
                summary=f"{action} {values.path}",
                diff=patch,
            )
        ):
            return ToolResult(ok=False, code="APPROVAL_DENIED", summary="file write was denied")
        current_path = context.workspace.resolve(values.path, must_exist=exists, file_only=True)
        if current_path != path or (not exists and current_path.exists()):
            return ToolResult(
                ok=False,
                code="PATH_CONFLICT",
                summary="file path changed while approval was pending",
                retryable=True,
            )
        if exists and sha256_file(current_path) != actual_hash:
            return ToolResult(
                ok=False,
                code="HASH_CONFLICT",
                summary="file changed while approval was pending",
                retryable=True,
            )
        atomic_write_text(path, values.content)
        new_hash = sha256_text(values.content)
        context.working.modified_files[values.path] = new_hash
        change = _record_change(
            context,
            path=values.path,
            kind="modified" if exists else "created",
            before_text=before if exists else None,
            after_sha256=new_hash,
            diff=patch,
            reversible=not truncated,
        )
        return ToolResult(
            ok=True,
            code="OK",
            summary=(f"overwrote {values.path}" if exists else f"created {values.path}"),
            data={
                "path": values.path,
                "sha256": new_hash,
                "diff": patch,
                "change_id": change.id,
                "change_kind": change.kind,
                "reversible": change.reversible,
            },
            truncated=truncated,
        )
