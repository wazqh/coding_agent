from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from coding_agent.project import project_id
from coding_agent.safety.paths import atomic_write_text


class WorkspaceSettingsError(ValueError):
    pass


class VerificationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commands: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("commands")
    @classmethod
    def validate_commands(cls, commands: list[str]) -> list[str]:
        normalized: list[str] = []
        for command in commands:
            value = command.strip()
            if not value or len(value) > 20_000 or "\n" in value or "\r" in value:
                raise ValueError(
                    "verification commands must be non-empty single-line values "
                    "of at most 20000 characters"
                )
            normalized.append(value)
        return normalized


class WorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_steps: int | None = Field(default=None, ge=12, le=100)
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
            return WorkspaceSettings.model_validate(value)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise WorkspaceSettingsError(f"cannot read workspace settings: {exc}") from exc

    def _save(self, settings: WorkspaceSettings) -> None:
        payload = settings.model_dump(mode="json", exclude_none=True)
        atomic_write_text(self.path, json.dumps(payload, indent=2) + "\n")

    def set_max_steps(self, value: int) -> None:
        if not 12 <= value <= 100:
            raise WorkspaceSettingsError("max steps must be between 12 and 100")
        settings = self.load()
        settings.max_steps = value
        self._save(settings)

    def reset_max_steps(self) -> None:
        settings = self.load()
        settings.max_steps = None
        self._save(settings)

    def set_verification_commands(self, commands: list[str]) -> None:
        try:
            verification = VerificationSettings(commands=commands)
        except ValidationError as exc:
            raise WorkspaceSettingsError(f"invalid verification configuration: {exc}") from exc
        settings = self.load()
        settings.verification = verification
        self._save(settings)

    def reset_verification_commands(self) -> None:
        settings = self.load()
        settings.verification = VerificationSettings()
        self._save(settings)
