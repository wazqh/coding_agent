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


class SessionStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "sessions"

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
            sessions.append(
                {
                    "id": path.stem,
                    "updated_at": records[-1]["timestamp"] if records else "",
                    "title": first_user[:80],
                    "records": len(records),
                    "workspace": str(metadata.get("workspace", "")),
                    "model": str(configuration.get("model", metadata.get("model", ""))),
                }
            )
        return sorted(sessions, key=lambda item: str(item["updated_at"]), reverse=True)
