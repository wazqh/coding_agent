from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from coding_agent.project import project_id
from coding_agent.safety.paths import atomic_write_text


class WorkspaceSettingsError(ValueError):
    pass


class WorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_steps: int | None = Field(default=None, ge=12, le=100)


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
