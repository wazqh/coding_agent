from __future__ import annotations

from pathlib import Path

import pytest

import coding_agent.workspace_settings as workspace_settings
from coding_agent.workspace_settings import WorkspaceSettingsError, WorkspaceSettingsStore


def test_workspace_max_steps_round_trips_without_writing_to_repository(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    data_dir = tmp_path / "data"
    store = WorkspaceSettingsStore(data_dir=data_dir, workspace=workspace)

    store.set_max_steps(30)

    assert store.load().max_steps == 30
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


@pytest.mark.parametrize("value", [29, 1000])
def test_workspace_max_steps_reject_invalid_bounds(tmp_path: Path, value: int) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)

    with pytest.raises(WorkspaceSettingsError, match=r"30.*999"):
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


def test_workspace_verification_mode_round_trips_with_tdd_guidance(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)

    store.set_verification(
        enabled=True,
        agent_tdd=True,
        commands=["python -m pytest -q"],
    )

    verification = store.load().verification
    assert verification.enabled is True
    assert verification.agent_tdd is True
    assert verification.commands == ["python -m pytest -q"]


def test_structured_verification_checks_round_trip_with_project_cwd(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "algorithm_practice").mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)

    store.set_verification_checks(
        enabled=True,
        agent_tdd=True,
        checks=[
            workspace_settings.VerificationCheck(
                id="algorithm-tests",
                label="算法练习测试",
                kind="test",
                command="python -m pytest tests -q",
                cwd="algorithm_practice",
                timeout_seconds=90,
            )
        ],
    )

    verification = store.load().verification
    assert verification.commands == ["python -m pytest tests -q"]
    assert verification.checks[0].model_dump() == {
        "id": "algorithm-tests",
        "label": "算法练习测试",
        "kind": "test",
        "command": "python -m pytest tests -q",
        "cwd": "algorithm_practice",
        "timeout_seconds": 90,
        "enabled": True,
        "source": "user",
        "target_paths": [],
    }


def test_legacy_verification_commands_migrate_to_root_checks(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        '{"verification":{"commands":["python -m pytest -q"]}}',
        encoding="utf-8",
    )

    verification = store.load().verification

    assert verification.enabled is True
    assert verification.commands == ["python -m pytest -q"]
    assert verification.checks[0].cwd == "."
    assert verification.checks[0].kind == "custom"
    assert verification.checks[0].id == "legacy-1"


@pytest.mark.parametrize("cwd", ["../outside", "/tmp", "C:\\outside", "nested/../../outside"])
def test_verification_checks_reject_working_directories_outside_workspace(
    tmp_path: Path,
    cwd: str,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)

    with pytest.raises(WorkspaceSettingsError, match="verification"):
        store.set_verification_checks(
            enabled=True,
            agent_tdd=False,
            checks=[
                {
                    "id": "unsafe",
                    "label": "Unsafe",
                    "kind": "custom",
                    "command": "python -m pytest -q",
                    "cwd": cwd,
                }
            ],
        )


def test_legacy_verification_commands_remain_enabled_after_upgrade(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        '{"verification":{"commands":["python -m pytest -q"]}}',
        encoding="utf-8",
    )

    verification = store.load().verification

    assert verification.enabled is True
    assert verification.agent_tdd is False
    assert verification.commands == ["python -m pytest -q"]


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


def test_agent_verification_registration_is_upserted_without_losing_user_settings(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = WorkspaceSettingsStore(data_dir=tmp_path / "data", workspace=workspace)
    store.set_verification_checks(
        enabled=True,
        agent_tdd=True,
        checks=[
            {
                "id": "user-lint",
                "label": "Lint",
                "kind": "lint",
                "command": "python -m ruff check .",
            }
        ],
    )

    registered = store.upsert_verification_check(
        {
            "id": "agent-algorithm-tests",
            "label": "Algorithm tests",
            "kind": "test",
            "command": "python -m pytest tests -q",
            "cwd": "algorithm_practice",
            "source": "agent",
            "target_paths": ["algorithm_practice"],
        },
        enable_verification=True,
    )
    updated = store.upsert_verification_check(
        {
            **registered.model_dump(mode="json"),
            "command": "python -m pytest tests -q -x",
        },
        enable_verification=True,
    )

    verification = store.load().verification
    assert verification.enabled is True
    assert verification.agent_tdd is True
    assert [check.id for check in verification.checks] == [
        "user-lint",
        "agent-algorithm-tests",
    ]
    assert updated.command == "python -m pytest tests -q -x"
    assert verification.checks[1] == updated
