from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from coding_agent.safety.paths import atomic_write_text


class SessionError(ValueError):
    pass


SESSION_ID = re.compile(r"^[0-9a-f]{24}$")


def concise_session_title(task: str, *, limit: int = 24) -> str:
    value = re.sub(r"\s+", " ", task).strip()
    value = re.sub(r"^(?:请帮我|麻烦|帮我|请)\s*", "", value)
    value = re.split(
        r"[\u3002\uff01\uff1f!?\n]|(?:，|,)(?=\s|然后|并且)",
        value,
        maxsplit=1,
    )[0].strip()
    if not value:
        return "未命名任务"
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


class SessionStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.directory = data_dir / "sessions"
        self._projects_path = data_dir / "hidden-projects.json"

    def hidden_workspaces(self) -> set[str]:
        if not self._projects_path.is_file():
            return set()
        try:
            value = json.loads(self._projects_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        if not isinstance(value, list):
            return set()
        return {str(item) for item in value if isinstance(item, str)}

    def set_workspace_hidden(self, workspace: Path, hidden: bool) -> None:
        resolved = str(workspace.resolve())
        values = self.hidden_workspaces()
        if hidden:
            values.add(resolved)
        else:
            values.discard(resolved)
        self._projects_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self._projects_path,
            json.dumps(sorted(values), ensure_ascii=False, indent=2) + "\n",
        )

    def create(self, metadata: dict[str, Any] | None = None) -> str:
        session_id = uuid4().hex[:24]
        self.append(session_id, "session", {"action": "created", **(metadata or {})})
        return session_id

    def _path(self, session_id: str) -> Path:
        if not SESSION_ID.fullmatch(session_id):
            raise SessionError("invalid session id")
        return self.directory / f"{session_id}.jsonl"

    def append(self, session_id: str, record_type: str, data: dict[str, Any]) -> None:
        path = self._path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "type": record_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            stream.flush()

    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        self.append(session_id, "message", message)

    def ensure_title(self, session_id: str, task: str) -> str:
        records = self.replay(session_id)
        existing = next(
            (
                str(record["data"].get("title", ""))
                for record in reversed(records)
                if record["type"] == "session_title" and isinstance(record["data"], dict)
            ),
            "",
        )
        if existing:
            return existing
        title = concise_session_title(task)
        self.append(session_id, "session_title", {"title": title})
        return title

    def replay(self, session_id: str) -> list[dict[str, Any]]:
        path = self._path(session_id)
        if not path.is_file():
            raise SessionError(f"session not found: {session_id}")
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SessionError(f"corrupt session line {line_number}") from exc
                if not isinstance(value, dict) or "type" not in value or "data" not in value:
                    raise SessionError(f"invalid session line {line_number}")
                records.append(value)
        return records

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        return [record["data"] for record in self.replay(session_id) if record["type"] == "message"]

    def delete(self, session_id: str) -> str:
        """Delete one session and return its exact JSONL payload for rollback."""

        path = self._path(session_id)
        if not path.is_file():
            raise SessionError(f"session not found: {session_id}")
        payload = path.read_text(encoding="utf-8")
        path.unlink()
        return payload

    def restore(self, session_id: str, payload: str) -> None:
        """Restore a session deleted by :meth:`delete` without overwriting another writer."""

        path = self._path(session_id)
        if path.exists():
            raise SessionError(f"session already exists: {session_id}")
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, payload)

    def list(self) -> list[dict[str, Any]]:
        if not self.directory.is_dir():
            return []
        sessions: list[dict[str, Any]] = []
        for path in self.directory.glob("*.jsonl"):
            try:
                records = self.replay(path.stem)
            except SessionError:
                continue
            first_user = next(
                (
                    str(item["data"].get("content", ""))
                    for item in records
                    if item["type"] == "message" and item["data"].get("role") == "user"
                ),
                "",
            )
            metadata = next(
                (
                    item["data"]
                    for item in records
                    if item["type"] == "session" and isinstance(item["data"], dict)
                ),
                {},
            )
            configuration = next(
                (
                    item["data"]
                    for item in reversed(records)
                    if item["type"] == "configuration" and isinstance(item["data"], dict)
                ),
                {},
            )
            explicit_title = next(
                (
                    str(item["data"].get("title", ""))
                    for item in reversed(records)
                    if item["type"] == "session_title" and isinstance(item["data"], dict)
                ),
                "",
            )
            sessions.append(
                {
                    "id": path.stem,
                    "updated_at": records[-1]["timestamp"] if records else "",
                    "title": explicit_title or concise_session_title(first_user),
                    "has_user_message": bool(first_user.strip()),
                    "records": len(records),
                    "workspace": str(metadata.get("workspace", "")),
                    "model": str(configuration.get("model", metadata.get("model", ""))),
                }
            )
        return sorted(sessions, key=lambda item: str(item["updated_at"]), reverse=True)
