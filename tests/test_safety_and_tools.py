from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from coding_agent.events import ToolResult
from coding_agent.safety.approval import ApprovalDecision, ApprovalPolicy, ApprovalRequest
from coding_agent.safety.commands import CommandPolicy, run_subprocess, sanitized_environment
from coding_agent.safety.paths import PathSafetyError, WorkspacePaths, sha256_file
from coding_agent.tools import filesystem as filesystem_tools
from coding_agent.tools.base import ToolContext, WorkingState
from coding_agent.tools.registry import default_registry


def context(
    root: Path,
    *,
    mode: str = "auto",
    interactive: bool = True,
    approval_callback: Callable[[ApprovalRequest], ApprovalDecision] | None = None,
    verification_command: tuple[str, str] | None = None,
) -> ToolContext:
    return ToolContext(
        workspace=WorkspacePaths(root),
        approval=ApprovalPolicy(mode, interactive=interactive, callback=approval_callback),
        session_id="a" * 24,
        turn_id="turn",
        working=WorkingState(),
        verification_command=verification_command,
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


def test_created_file_change_is_recorded_and_can_undo_the_visible_diff(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    result = default_registry().execute(
        "write_file",
        {"path": "created.txt", "content": "created by agent\n"},
        ctx,
    )

    assert result.ok
    assert result.data["change_kind"] == "created"
    assert len(ctx.working.changes) == 1
    assert ctx.working.changes[0].diff == result.data["diff"]
    undo_change = getattr(filesystem_tools, "undo_change", None)
    assert callable(undo_change)

    undone = undo_change(ctx.working, ctx.workspace, result.data["change_id"])

    assert undone.path == "created.txt"
    assert not (tmp_path / "created.txt").exists()
    assert ctx.working.changes == []
    assert ctx.working.diffs == []


def test_undo_rejects_a_stale_diff_without_overwriting_newer_content(tmp_path: Path) -> None:
    path = tmp_path / "demo.py"
    path.write_text("value = 1\n", encoding="utf-8")
    ctx = context(tmp_path)
    registry = default_registry()
    first = registry.execute(
        "edit_file",
        {
            "path": "demo.py",
            "old_text": "1",
            "new_text": "2",
            "expected_sha256": sha256_file(path),
        },
        ctx,
    )
    second = registry.execute(
        "edit_file",
        {
            "path": "demo.py",
            "old_text": "2",
            "new_text": "3",
            "expected_sha256": sha256_file(path),
        },
        ctx,
    )
    undo_change = getattr(filesystem_tools, "undo_change", None)
    assert callable(undo_change)

    with pytest.raises(ValueError, match="changed since this Diff was recorded"):
        undo_change(ctx.working, ctx.workspace, first.data["change_id"])
    assert path.read_text(encoding="utf-8") == "value = 3\n"

    undo_change(ctx.working, ctx.workspace, second.data["change_id"])
    undo_change(ctx.working, ctx.workspace, first.data["change_id"])
    assert path.read_text(encoding="utf-8") == "value = 1\n"


def test_undo_is_disabled_when_the_reviewed_diff_was_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(filesystem_tools, "MAX_DIFF_CHARS", 80)
    ctx = context(tmp_path)
    result = default_registry().execute(
        "write_file",
        {"path": "large.txt", "content": "\n".join(f"line {index}" for index in range(100))},
        ctx,
    )

    assert result.ok and result.truncated
    assert ctx.working.changes[0].reversible is False
    with pytest.raises(ValueError, match="truncated"):
        filesystem_tools.undo_change(ctx.working, ctx.workspace, result.data["change_id"])
    assert (tmp_path / "large.txt").is_file()


def test_change_history_bounds_undo_backups_and_visible_diffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(filesystem_tools, "MAX_CHANGE_HISTORY", 2)
    monkeypatch.setattr(filesystem_tools, "MAX_UNDO_BACKUP_CHARS", 5)
    path = tmp_path / "bounded.txt"
    path.write_text("first value\n", encoding="utf-8")
    ctx = context(tmp_path)
    registry = default_registry()

    for old, new in [("first", "second"), ("second", "third"), ("third", "fourth")]:
        result = registry.execute(
            "edit_file",
            {
                "path": "bounded.txt",
                "old_text": old,
                "new_text": new,
                "expected_sha256": sha256_file(path),
            },
            ctx,
        )
        assert result.ok

    assert len(ctx.working.changes) == 2
    assert len(ctx.working.diffs) == 2
    assert all(change.before_text is None for change in ctx.working.changes)
    assert all(change.reversible is False for change in ctx.working.changes)


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
    reset = policy.classify("git reset --hard HEAD")
    assert not reset.allowed
    assert reset.rule_id == "git-reset-hard"
    assert reset.risk_label == "破坏性 Git 重置"
    assert reset.matched_text == "git reset --hard"
    assert "保留工作区改动" in reset.guidance
    assert not policy.classify("Remove-Item x -Recurse").allowed
    assert not policy.classify("shutdown /s").allowed
    assert not policy.classify("git status; shutdown /s").allowed
    assert not policy.classify("format C:").allowed
    assert not policy.classify("cmd /c format D:").allowed
    assert policy.classify("python -m ruff format --check .").allowed
    assert policy.classify("ruff format --check .").approval_required
    assert policy.classify("git status; echo x").approval_required
    assert not policy.classify("git status").approval_required
    assert policy.classify("pytest -q").approval_required
    environment = sanitized_environment({"PATH": "ok", "API_TOKEN": "bad", "password": "bad"})
    assert environment == {"PATH": "ok"}
    command = f'"{sys.executable}" -c "print(123)"'
    result = run_subprocess(command, cwd=tmp_path, timeout=10, environ=os.environ)
    assert result["exit_code"] == 0 and "123" in result["stdout"]


@pytest.mark.parametrize(
    "command",
    [
        'echo "git reset --hard HEAD"',
        "echo rm -rf build",
        "python -c \"print('shutdown')\"",
        "python -m ruff format --check .",
        "ruff format --check .",
        "npm run format",
        "git show --format=fuller HEAD",
        "git clean -nfd",
        "git clean --dry-run --force -d",
        "Remove-Item build -Recurse -WhatIf",
        "Remove-Item build -Recurse:$false",
        "dd if=image.bin of=backup.img",
        "mkfs.ext4 filesystem.img",
        "systemctl status",
        "systemctl --dry-run reboot",
        "shutdown /a",
        "shutdown -c",
        "Stop-Computer -WhatIf",
        "wipefs --no-act /dev/sda",
        "Clear-Disk -Number 0 -WhatIf",
        "powershell -Command \"Write-Host 'shutdown /s'\"",
        "bash -c 'echo rm -rf build'",
        'rg "Remove-Item.*-Recurse" .',
    ],
)
def test_command_policy_does_not_block_danger_words_used_as_data(command: str) -> None:
    classification = CommandPolicy().classify(command)

    assert classification.allowed is True
    assert classification.rule_id is None


@pytest.mark.parametrize(
    ("command", "rule_id"),
    [
        ("git -C repo reset --hard HEAD", "git-reset-hard"),
        ("sudo git clean -fd", "git-clean-force"),
        ("git clean --force -d", "git-clean-force"),
        ("echo ok && rm -rf build", "recursive-delete"),
        ("Remove-Item build -Recurse:$true -Force", "recursive-delete"),
        ('powershell -Command "Get-ChildItem x | Remove-Item -Recurse -Force"', "recursive-delete"),
        ('cmd /c "format C:"', "disk-format"),
        ("Format-Volume -DriveLetter C -Force", "disk-format"),
        ("mkfs.ext4 /dev/sda1", "disk-format"),
        ("Clear-Disk -Number 0 -RemoveData", "direct-disk-write"),
        ("bash -c 'shutdown -h now'", "system-power"),
        ("systemctl reboot", "system-power"),
        ("init 0", "system-power"),
        ("dd if=image.bin of=/dev/sda", "direct-disk-write"),
        ("wipefs --all /dev/sda", "direct-disk-write"),
        ("tee /dev/sda", "direct-disk-write"),
        ("Set-Content -Path \\\\.\\PhysicalDrive0 -Value x", "direct-disk-write"),
        ("powershell -EncodedCommand ZABpAHIA", "encoded-shell-payload"),
        ('eval "rm -rf build"', "recursive-delete"),
        ("xargs rm -rf", "recursive-delete"),
        ("find . -exec rm -rf {} +", "recursive-delete"),
        ('Invoke-Expression "Remove-Item build -Recurse"', "recursive-delete"),
        ("FOO=bar rm -rf build", "recursive-delete"),
        ("command -- rm -rf build", "recursive-delete"),
        ("sudo -u root rm -rf build", "recursive-delete"),
        ("env -i FOO=bar rm -rf build", "recursive-delete"),
        ("git --git-dir=.git reset --hard HEAD", "git-reset-hard"),
        ("git --no-pager reset --hard HEAD", "git-reset-hard"),
        ("xargs -n 1 rm -rf", "recursive-delete"),
        ("del /s build", "recursive-delete"),
        (":(){ :|:& };:", "fork-bomb"),
    ],
)
def test_command_policy_blocks_semantic_destructive_invocations(
    command: str,
    rule_id: str,
) -> None:
    classification = CommandPolicy().classify(command)

    assert classification.allowed is False
    assert classification.rule_id == rule_id
    assert classification.matched_text


def test_run_command_executes_in_a_confined_workspace_relative_directory(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "algorithm_practice"
    nested.mkdir()
    command = f'"{sys.executable}" -c "import os; print(os.getcwd())"'

    result = default_registry().execute(
        "run_command",
        {"command": command, "cwd": "algorithm_practice"},
        context(tmp_path),
    )

    assert result.ok is True
    assert result.data["cwd"] == "algorithm_practice"
    assert str(nested.resolve()) in result.data["stdout"]


def test_saved_verification_rule_authorizes_only_its_exact_command_and_cwd(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "feature"
    nested.mkdir()
    command = f'"{sys.executable}" -c "print(\'verified\')"'
    approvals: list[object] = []
    ctx = context(
        tmp_path,
        mode="prompt",
        approval_callback=lambda request: approvals.append(request) or ApprovalDecision.DENY,
        verification_command=(command, "feature"),
    )

    exact = default_registry().execute(
        "run_command",
        {"command": command, "cwd": "feature"},
        ctx,
    )
    wrong_cwd = default_registry().execute(
        "run_command",
        {"command": command, "cwd": "."},
        ctx,
    )

    assert exact.ok is True
    assert exact.data["stdout"].strip() == "verified"
    assert wrong_cwd.code == "APPROVAL_DENIED"
    assert len(approvals) == 1


def test_saved_verification_rule_never_overrides_a_hard_safety_block(tmp_path: Path) -> None:
    approvals: list[object] = []
    ctx = context(
        tmp_path,
        mode="prompt",
        approval_callback=lambda request: approvals.append(request) or ApprovalDecision.ALLOW_ONCE,
        verification_command=("git clean -fd", "."),
    )

    result = default_registry().execute(
        "run_command",
        {"command": "git clean -fd", "cwd": "."},
        ctx,
    )

    assert result.code == "DANGEROUS_COMMAND"
    assert result.data["hard_blocked"] is True
    assert approvals == []


@pytest.mark.parametrize("cwd", ["../outside", "/tmp", "C:\\outside"])
def test_run_command_rejects_working_directories_outside_workspace(
    tmp_path: Path,
    cwd: str,
) -> None:
    result = default_registry().execute(
        "run_command",
        {"command": "python -m pytest -q", "cwd": cwd},
        context(tmp_path),
    )

    assert result.code == "TOOL_ERROR"
    assert any(term in result.summary for term in ("workspace", "absolute", "cannot resolve"))


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
    assert denied.data == {
        "command": "git clean -fd",
        "cwd": ".",
        "hard_blocked": True,
        "rule_id": "git-clean-force",
        "risk_label": "强制清理 Git 工作区",
        "matched_text": "git clean -fd",
        "guidance": "先查看 git status 和 git clean -nd，再让用户确认精确目标。",
    }


def test_command_policy_allows_non_destructive_executor_and_device_cases() -> None:
    policy = CommandPolicy()

    assert policy.classify("find . -maxdepth 1").allowed is True
    assert policy.classify("dd if=image.bin of=/dev/null").allowed is True


def test_run_subprocess_honors_cancellation_before_launch(tmp_path: Path) -> None:
    result = run_subprocess(
        f'"{sys.executable}" -c "print(\'must not run\')"',
        cwd=tmp_path,
        timeout=10,
        cancel_requested=lambda: True,
    )

    assert result == {
        "exit_code": 130,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "cancelled": True,
        "truncated": False,
    }


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
    invalid.model_dump_json()


def test_default_registry_exposes_structured_verification_registration() -> None:
    registry = default_registry()

    assert "register_verification" in registry.names()
    schema = next(
        item for item in registry.schemas() if item["function"]["name"] == "register_verification"
    )
    properties = schema["function"]["parameters"]["properties"]
    assert {"command", "cwd", "target_paths", "timeout_seconds"} <= properties.keys()
    assert "run_verify" in registry.names()
    run_schema = next(
        item for item in registry.schemas() if item["function"]["name"] == "run_verify"
    )
    assert set(run_schema["function"]["parameters"]["properties"]) == {"rule_id"}
