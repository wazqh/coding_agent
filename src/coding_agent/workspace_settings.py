from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from coding_agent.config import MAX_AGENT_STEPS, MIN_AGENT_STEPS
from coding_agent.project import project_id
from coding_agent.safety.paths import atomic_write_text


class WorkspaceSettingsError(ValueError):
    pass


def _workspace_relative_path(raw_value: str, *, field_name: str) -> str:
    """Normalize a workspace-relative path without trusting the host OS parser alone."""
    value = raw_value.strip() or "."
    posix_path = PurePosixPath(value.replace("\\", "/"))
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in posix_path.parts
        or ".." in windows_path.parts
    ):
        raise ValueError(f"verification {field_name} must stay inside the workspace")
    return posix_path.as_posix()


class VerificationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["test", "build", "lint", "typecheck", "custom"] = "custom"
    command: str
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    enabled: bool = True
    source: Literal["user", "agent"] = "user"
    target_paths: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("label", "command")
    @classmethod
    def validate_single_line_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 20_000 or "\n" in normalized or "\r" in normalized:
            raise ValueError("verification text must be a non-empty single-line value")
        return normalized

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, cwd: str) -> str:
        return _workspace_relative_path(cwd, field_name="cwd")

    @field_validator("target_paths")
    @classmethod
    def validate_target_paths(cls, paths: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_path in paths:
            display = _workspace_relative_path(raw_path, field_name="target paths")
            if display not in normalized:
                normalized.append(display)
        return normalized


class VerificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    agent_tdd: bool = False
    checks: list[VerificationCheck] = Field(default_factory=list, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_commands(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        commands = payload.pop("commands", None)
        if "checks" not in payload and isinstance(commands, list):
            payload["checks"] = [
                {
                    "id": f"legacy-{index}",
                    "label": f"Verification {index}",
                    "kind": "custom",
                    "command": command,
                    "cwd": ".",
                }
                for index, command in enumerate(commands, start=1)
            ]
        return payload

    @property
    def commands(self) -> list[str]:
        return [check.command for check in self.checks if check.enabled]


class WorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_steps: int | None = Field(
        default=None,
        ge=MIN_AGENT_STEPS,
        le=MAX_AGENT_STEPS,
    )
    verification: VerificationSettings = Field(default_factory=VerificationSettings)


class WorkspaceSettingsStore:
    def __init__(self, *, data_dir: Path, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.path = data_dir / "workspaces" / f"{project_id(self.workspace)}.json"

    def load(self) -> WorkspaceSettings:
        if not self.path.is_file():
            return WorkspaceSettings()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("verification"), dict):
                verification = value["verification"]
                if "enabled" not in verification:
                    verification["enabled"] = bool(
                        verification.get("checks") or verification.get("commands")
                    )
                verification.setdefault("agent_tdd", False)
            return WorkspaceSettings.model_validate(value)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise WorkspaceSettingsError(f"cannot read workspace settings: {exc}") from exc

    def _save(self, settings: WorkspaceSettings) -> None:
        payload = settings.model_dump(mode="json", exclude_none=True)
        atomic_write_text(self.path, json.dumps(payload, indent=2) + "\n")

    def set_max_steps(self, value: int) -> None:
        if not MIN_AGENT_STEPS <= value <= MAX_AGENT_STEPS:
            raise WorkspaceSettingsError(
                f"max steps must be between {MIN_AGENT_STEPS} and {MAX_AGENT_STEPS}"
            )
        settings = self.load()
        settings.max_steps = value
        self._save(settings)

    def reset_max_steps(self) -> None:
        settings = self.load()
        settings.max_steps = None
        self._save(settings)

    def set_verification_commands(self, commands: list[str]) -> None:
        current = self.load().verification
        self.set_verification(
            enabled=bool(commands),
            agent_tdd=current.agent_tdd,
            commands=commands,
        )

    def set_verification(
        self,
        *,
        enabled: bool,
        agent_tdd: bool,
        commands: list[str],
    ) -> None:
        checks: list[dict[str, object]] = [
            {
                "id": f"legacy-{index}",
                "label": f"Verification {index}",
                "command": command,
            }
            for index, command in enumerate(commands, start=1)
        ]
        self.set_verification_checks(
            enabled=enabled,
            agent_tdd=agent_tdd,
            checks=checks,
        )

    def set_verification_checks(
        self,
        *,
        enabled: bool,
        agent_tdd: bool,
        checks: Sequence[VerificationCheck | dict[str, object]],
    ) -> None:
        try:
            validated_checks = [VerificationCheck.model_validate(check) for check in checks]
            verification = VerificationSettings(
                enabled=enabled,
                agent_tdd=agent_tdd,
                checks=validated_checks,
            )
        except ValidationError as exc:
            raise WorkspaceSettingsError(f"invalid verification configuration: {exc}") from exc
        settings = self.load()
        settings.verification = verification
        self._save(settings)

    def upsert_verification_check(
        self,
        check: VerificationCheck | dict[str, object],
        *,
        enable_verification: bool,
        agent_tdd: bool | None = None,
    ) -> VerificationCheck:
        settings = self.load()
        try:
            validated = VerificationCheck.model_validate(check)
            checks = list(settings.verification.checks)
            match = next(
                (index for index, current in enumerate(checks) if current.id == validated.id),
                None,
            )
            if match is None:
                checks.append(validated)
            else:
                checks[match] = validated
            verification = VerificationSettings(
                enabled=settings.verification.enabled or enable_verification,
                agent_tdd=(settings.verification.agent_tdd if agent_tdd is None else agent_tdd),
                checks=checks,
            )
        except ValidationError as exc:
            raise WorkspaceSettingsError(f"invalid verification configuration: {exc}") from exc
        settings.verification = verification
        self._save(settings)
        return validated

    def reset_verification_commands(self) -> None:
        settings = self.load()
        settings.verification = VerificationSettings()
        self._save(settings)
