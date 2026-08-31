from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.workspace_settings import WorkspaceSettingsError, WorkspaceSettingsStore


def test_workspace_max_steps_round_trips_without_writing_to_repository(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    data_dir = tmp_path / "data"
    store = WorkspaceSettingsStore(data_dir=data_dir, workspace=workspace)

    store.set_max_steps(12)

    assert store.load().max_steps == 12
    assert store.path.parent == data_dir / "workspaces"
    assert not (workspace / "coding-agent.toml").exists()


def test_workspace_max_steps_are_isolated_by_project(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / ".git").mkdir()
    (second / ".git").mkdir()
    first_store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=first)
    second_store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=second)

    first_store.set_max_steps(40)

    assert first_store.load().max_steps == 40
    assert second_store.load().max_steps is None
    assert first_store.path != second_store.path


@pytest.mark.parametrize("value", [11, 101])
def test_workspace_max_steps_reject_invalid_bounds(tmp_path: Path, value: int) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)

    with pytest.raises(WorkspaceSettingsError, match=r"12.*100"):
        store.set_max_steps(value)

    assert store.load().max_steps is None


def test_reset_removes_workspace_max_steps_override(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)
    store.set_max_steps(32)

    store.reset_max_steps()

    assert store.load().max_steps is None


def test_workspace_verification_commands_round_trip_and_remain_project_scoped(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / ".git").mkdir()
    (second / ".git").mkdir()
    data_dir = tmp_path / "data"
    first_store = WorkspaceSettingsStore(data_dir=data_dir, workspace=first)
    second_store = WorkspaceSettingsStore(data_dir=data_dir, workspace=second)

    first_store.set_verification_commands(["python -m pytest -q", "python -m ruff check ."])

    assert first_store.load().verification.commands == [
        "python -m pytest -q",
        "python -m ruff check .",
    ]
    assert second_store.load().verification.commands == []
    assert not (first / "coding-agent.toml").exists()


@pytest.mark.parametrize(
    "commands",
    [
        [""],
        ["   "],
        ["python -m pytest\nRemove-Item -Recurse ."],
        ["x" * 20_001],
        [f"check-{index}" for index in range(9)],
    ],
)
def test_workspace_verification_commands_reject_malformed_values(
    tmp_path: Path,
    commands: list[str],
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)

    with pytest.raises(WorkspaceSettingsError, match="verification"):
        store.set_verification_commands(commands)

    assert store.load().verification.commands == []


def test_reset_removes_workspace_verification_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)
    store.set_verification_commands(["python -m pytest -q"])

    store.reset_verification_commands()

    assert store.load().verification.commands == []
