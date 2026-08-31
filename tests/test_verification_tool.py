from __future__ import annotations

from pathlib import Path

from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.safety.paths import WorkspacePaths
from coding_agent.tools.base import ToolContext, WorkingState
from coding_agent.tools.filesystem import WriteFileTool
from coding_agent.tools.verification import RegisterVerificationArgs, RegisterVerificationTool
from coding_agent.workspace_settings import VerificationCheck


def _context(
    workspace: Path,
    *,
    working: WorkingState | None = None,
    registrar: list[VerificationCheck] | None = None,
) -> ToolContext:
    registered = registrar if registrar is not None else []

    def register(check: VerificationCheck) -> VerificationCheck:
        registered.append(check)
        return check

    return ToolContext(
        workspace=WorkspacePaths(workspace),
        approval=ApprovalPolicy("auto"),
        session_id="session",
        turn_id="turn-1",
        working=working or WorkingState(),
        verification_registrar=register,
    )


def test_write_file_records_created_parent_directories(tmp_path: Path) -> None:
    working = WorkingState()
    context = _context(tmp_path, working=working)

    result = WriteFileTool().execute(
        WriteFileTool.args_model(
            path="algorithm_practice/tests/test_trap.py",
            content="def test_trap():\n    assert True\n",
        ),
        context,
    )

    assert result.ok is True
    assert result.data["created_directories"] == [
        "algorithm_practice",
        "algorithm_practice/tests",
    ]
    assert working.changes[-1].turn_id == "turn-1"
    assert working.changes[-1].created_directories == [
        "algorithm_practice",
        "algorithm_practice/tests",
    ]


def test_register_verification_uses_an_explicit_project_root_and_records_artifacts(
    tmp_path: Path,
) -> None:
    working = WorkingState()
    registered: list[VerificationCheck] = []
    context = _context(tmp_path, working=working, registrar=registered)
    WriteFileTool().execute(
        WriteFileTool.args_model(
            path="algorithm_practice/tests/test_trap.py",
            content="def test_trap():\n    assert True\n",
        ),
        context,
    )

    result = RegisterVerificationTool().execute(
        RegisterVerificationArgs(
            label="接雨水测试",
            kind="test",
            command="python -m pytest tests -q",
            cwd="algorithm_practice",
            timeout_seconds=90,
        ),
        context,
    )

    assert result.ok is True
    assert len(registered) == 1
    check = registered[0]
    assert check.source == "agent"
    assert check.cwd == "algorithm_practice"
    assert check.target_paths == ["algorithm_practice"]
    assert result.data["created_files"] == ["algorithm_practice/tests/test_trap.py"]
    assert result.data["created_directories"] == [
        "algorithm_practice",
        "algorithm_practice/tests",
    ]


def test_register_verification_rejects_a_missing_working_directory(tmp_path: Path) -> None:
    result = RegisterVerificationTool().execute(
        RegisterVerificationArgs(
            label="Missing tests",
            kind="test",
            command="python -m pytest -q",
            cwd="missing-project",
        ),
        _context(tmp_path),
    )

    assert result.ok is False
    assert result.code == "INVALID_VERIFICATION_ROOT"
    assert "does not exist" in result.summary
