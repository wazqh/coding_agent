from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from coding_agent.events import ToolResult
from coding_agent.safety.approval import ApprovalDecision, ApprovalPolicy
from coding_agent.safety.commands import CommandPolicy, run_subprocess, sanitized_environment
from coding_agent.safety.paths import PathSafetyError, WorkspacePaths, sha256_file
from coding_agent.tools.base import ToolContext, WorkingState
from coding_agent.tools.registry import default_registry


def context(root: Path, *, mode: str = "auto", interactive: bool = True) -> ToolContext:
    return ToolContext(
        workspace=WorkspacePaths(root),
        approval=ApprovalPolicy(mode, interactive=interactive),
        session_id="a" * 24,
        turn_id="turn",
        working=WorkingState(),
    )


def test_workspace_rejects_traversal_and_absolute(tmp_path: Path) -> None:
    paths = WorkspacePaths(tmp_path)
    with pytest.raises(PathSafetyError):
        paths.resolve("../outside.txt", must_exist=False)
    with pytest.raises(PathSafetyError):
        paths.resolve(str((tmp_path / "absolute").resolve()), must_exist=False)


def test_workspace_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks require privileges on this platform")
    with pytest.raises(PathSafetyError):
        WorkspacePaths(tmp_path).resolve("link/new.txt", must_exist=False)


def test_read_edit_write_hash_and_approval(tmp_path: Path) -> None:
    registry = default_registry()
    path = tmp_path / "demo.py"
    path.write_text("value = 1\n", encoding="utf-8")
    ctx = context(tmp_path)
    read = registry.execute("read_file", {"path": "demo.py"}, ctx)
    assert read.ok and read.data["sha256"] == sha256_file(path)
    conflict = registry.execute(
        "edit_file",
        {
            "path": "demo.py",
            "old_text": "value = 1",
            "new_text": "value = 2",
            "expected_sha256": "0" * 64,
        },
        ctx,
    )
    assert conflict.code == "HASH_CONFLICT"
    edited = registry.execute(
        "edit_file",
        {
            "path": "demo.py",
            "old_text": "value = 1",
            "new_text": "value = 2",
            "expected_sha256": read.data["sha256"],
        },
        ctx,
    )
    assert edited.ok and path.read_text(encoding="utf-8") == "value = 2\n"
    missing_hash = registry.execute("write_file", {"path": "demo.py", "content": "x\n"}, ctx)
    assert missing_hash.code == "HASH_REQUIRED"
    overwritten = registry.execute(
        "write_file",
        {
            "path": "demo.py",
            "content": "value = 3\n",
            "expected_sha256": edited.data["sha256"],
        },
        ctx,
    )
    assert overwritten.ok and path.read_text(encoding="utf-8") == "value = 3\n"
    created = registry.execute("write_file", {"path": "new.txt", "content": "new"}, ctx)
    assert created.ok and (tmp_path / "new.txt").read_text(encoding="utf-8") == "new"
    assert ctx.working.diffs


def test_unique_match_and_noninteractive_denial(tmp_path: Path) -> None:
    registry = default_registry()
    path = tmp_path / "same.txt"
    path.write_text("x x", encoding="utf-8")
    digest = sha256_file(path)
    result = registry.execute(
        "edit_file",
        {"path": "same.txt", "old_text": "x", "new_text": "y", "expected_sha256": digest},
        context(tmp_path),
    )
    assert result.code == "NON_UNIQUE_MATCH"
    denied = registry.execute(
        "write_file",
        {"path": "blocked.txt", "content": "no"},
        context(tmp_path, mode="prompt", interactive=False),
    )
    assert denied.code == "APPROVAL_DENIED"
    assert not (tmp_path / "blocked.txt").exists()


def test_session_approval_grant(tmp_path: Path) -> None:
    decisions = iter([ApprovalDecision.ALLOW_SESSION])
    policy = ApprovalPolicy("prompt", callback=lambda _: next(decisions))
    ctx = ToolContext(
        workspace=WorkspacePaths(tmp_path),
        approval=policy,
        session_id="a" * 24,
        turn_id="turn",
        working=WorkingState(),
    )
    registry = default_registry()
    assert registry.execute("write_file", {"path": "a.txt", "content": "1"}, ctx).ok
    digest = sha256_file(tmp_path / "a.txt")
    assert registry.execute(
        "write_file",
        {"path": "a.txt", "content": "2", "expected_sha256": digest},
        ctx,
    ).ok
    assert policy.session_grant_count == 1
    assert policy.set_mode("read-only")
    assert policy.session_grant_count == 0
    assert not policy.set_mode("read-only")
    with pytest.raises(ValueError, match="unknown permission mode"):
        policy.set_mode("unsafe")


def test_file_change_while_approval_pending_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "race.txt"
    path.write_text("before", encoding="utf-8")

    def mutate_during_approval(_: object) -> ApprovalDecision:
        path.write_text("external change", encoding="utf-8")
        return ApprovalDecision.ALLOW_ONCE

    ctx = ToolContext(
        workspace=WorkspacePaths(tmp_path),
        approval=ApprovalPolicy("prompt", callback=mutate_during_approval),
        session_id="a" * 24,
        turn_id="turn",
        working=WorkingState(),
    )
    result = default_registry().execute(
        "edit_file",
        {
            "path": "race.txt",
            "old_text": "before",
            "new_text": "agent change",
            "expected_sha256": sha256_file(path),
        },
        ctx,
    )
    assert result.code == "HASH_CONFLICT"
    assert path.read_text(encoding="utf-8") == "external change"


def test_command_policy_secret_filter_and_execution(tmp_path: Path) -> None:
    policy = CommandPolicy()
    assert not policy.classify("git reset --hard HEAD").allowed
    assert not policy.classify("Remove-Item x -Recurse").allowed
    assert not policy.classify("shutdown /s").allowed
    assert not policy.classify("git status; shutdown /s").allowed
    assert policy.classify("git status; echo x").approval_required
    assert not policy.classify("git status").approval_required
    assert policy.classify("pytest -q").approval_required
    environment = sanitized_environment({"PATH": "ok", "API_TOKEN": "bad", "password": "bad"})
    assert environment == {"PATH": "ok"}
    command = f'"{sys.executable}" -c "print(123)"'
    result = run_subprocess(command, cwd=tmp_path, timeout=10, environ=os.environ)
    assert result["exit_code"] == 0 and "123" in result["stdout"]


def test_command_timeout_output_bound_and_tool_rejection(tmp_path: Path) -> None:
    quote = '"'
    large_command = f"{quote}{sys.executable}{quote} -c {quote}print('x'*40000){quote}"
    large = run_subprocess(large_command, cwd=tmp_path, timeout=10)
    assert large["exit_code"] == 0
    assert large["truncated"]
    assert "output truncated" in large["stdout"]

    timeout_command = f"{quote}{sys.executable}{quote} -c {quote}import time; time.sleep(5){quote}"
    timed_out = run_subprocess(timeout_command, cwd=tmp_path, timeout=1)
    assert timed_out["timed_out"]

    checks = 0

    def cancel_command() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    started = time.monotonic()
    cancelled = run_subprocess(
        timeout_command,
        cwd=tmp_path,
        timeout=10,
        cancel_requested=cancel_command,
    )
    assert cancelled["cancelled"] and not cancelled["timed_out"]
    assert time.monotonic() - started < 5

    denied = default_registry().execute(
        "run_command",
        {"command": "git clean -fd"},
        context(tmp_path),
    )
    assert denied.code == "DANGEROUS_COMMAND"


def test_list_and_search_are_bounded_to_workspace(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "one.py").write_text("needle = 1\n", encoding="utf-8")
    (tmp_path / "src" / "two.txt").write_text("nothing\nneedle\n", encoding="utf-8")
    registry = default_registry()
    ctx = context(tmp_path)
    listed = registry.execute("list_files", {"path": "src", "pattern": "*", "max_results": 10}, ctx)
    searched = registry.execute(
        "search_text", {"path": "src", "pattern": "needle", "max_results": 10}, ctx
    )
    assert listed.ok and len(listed.data["entries"]) == 2
    assert searched.ok and len(searched.data["matches"]) == 2


def test_registry_argument_and_unknown_errors(tmp_path: Path) -> None:
    registry = default_registry()
    ctx = context(tmp_path)
    unknown = registry.execute("missing", {}, ctx)
    invalid = registry.execute("read_file", {}, ctx)
    assert unknown.code == "UNKNOWN_TOOL"
    assert invalid.code == "INVALID_ARGUMENTS"
    assert all(isinstance(item, ToolResult) for item in (unknown, invalid))
