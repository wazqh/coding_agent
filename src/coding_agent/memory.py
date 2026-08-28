from __future__ import annotations

import builtins
import importlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from coding_agent.project import project_id
from coding_agent.safety.paths import atomic_write_text


class MemoryError(ValueError):
    pass


class MemoryKind(StrEnum):
    PREFERENCE = "preference"
    COMMAND = "command"
    FACT = "fact"
    DECISION = "decision"
    CONSTRAINT = "constraint"


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    kind: MemoryKind
    content: str
    evidence_session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    enabled: bool = True


class MemoryCandidate(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    kind: MemoryKind
    content: str
    evidence_session_id: str
    confidence: float = Field(default=0.8, ge=0, le=1)


_ASSIGNMENT_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|token|password|passwd|secret|credential)\s*[:=]\s*['\"]?\S+"
)
_TOKEN_SECRET = re.compile(r"(?:sk|ghp|glpat|xox[baprs])-[A-Za-z0-9_-]{12,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_WORDS = re.compile(r"[A-Za-z0-9_./-]+|[\u4e00-\u9fff]")


def _validate_content(content: str) -> str:
    value = content.strip()
    if not value:
        raise MemoryError("memory content is empty")
    if len(value) > 1000:
        raise MemoryError("memory content exceeds 1000 characters")
    if _ASSIGNMENT_SECRET.search(value) or _TOKEN_SECRET.search(value) or _PRIVATE_KEY.search(value):
        raise MemoryError("memory content appears to contain a secret")
    if value.count("\n") > 20 or ("```" in value and len(value) > 400):
        raise MemoryError("large source-code blocks cannot be stored as memory")
    return value


def _token_count(text: str) -> int:
    try:
        tiktoken = importlib.import_module("tiktoken")
        encoded: builtins.list[int] = tiktoken.get_encoding("cl100k_base").encode(text)
        return len(encoded)
    except (ImportError, KeyError, AttributeError):
        return max(1, len(text) // 4)


class MemoryStore:
    def __init__(self, *, data_dir: Path, workspace: Path, enabled: bool = False) -> None:
        self.workspace = workspace.resolve()
        self.project_id = project_id(self.workspace)
        self.path = data_dir / "memory" / f"{self.project_id}.json"
        self.enabled = enabled

    def _load(self) -> list[MemoryRecord]:
        if not self.path.is_file():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, list):
                return []
            return [MemoryRecord.model_validate(item) for item in value]
        except (OSError, json.JSONDecodeError, ValueError):
            return []

    def _save(self, records: list[MemoryRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [record.model_dump(mode="json") for record in records]
        atomic_write_text(self.path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def list(self, *, include_disabled: bool = False) -> list[MemoryRecord]:
        records = self._load()
        return records if include_disabled else [record for record in records if record.enabled]

    def propose(
        self,
        *,
        kind: MemoryKind,
        content: str,
        evidence_session_id: str,
        confidence: float = 0.8,
    ) -> MemoryCandidate:
        return MemoryCandidate(
            kind=kind,
            content=_validate_content(content),
            evidence_session_id=evidence_session_id,
            confidence=confidence,
        )

    def approve(self, candidate: MemoryCandidate) -> MemoryRecord:
        content = _validate_content(candidate.content)
        records = self._load()
        normalized = " ".join(content.casefold().split())
        now = datetime.now(UTC)
        for record in records:
            if record.kind == candidate.kind and " ".join(record.content.casefold().split()) == normalized:
                record.enabled = True
                record.updated_at = now
                record.confidence = max(record.confidence, candidate.confidence)
                self._save(records)
                return record
        record = MemoryRecord(
            kind=candidate.kind,
            content=content,
            evidence_session_id=candidate.evidence_session_id,
            confidence=candidate.confidence,
        )
        records.append(record)
        self._save(records)
        return record

    def remember(self, *, content: str, session_id: str) -> MemoryRecord:
        candidate = self.propose(
            kind=MemoryKind.FACT,
            content=content,
            evidence_session_id=session_id,
            confidence=1.0,
        )
        return self.approve(candidate)

    def forget(self, memory_id: str) -> bool:
        records = self._load()
        changed = False
        for record in records:
            if record.id == memory_id and record.enabled:
                record.enabled = False
                record.updated_at = datetime.now(UTC)
                changed = True
        if changed:
            self._save(records)
        return changed

    def clear(self) -> None:
        self._save([])

    def query(
        self,
        text: str,
        *,
        paths: builtins.list[str] | None = None,
        max_items: int = 8,
        max_tokens: int = 2000,
    ) -> builtins.list[MemoryRecord]:
        if not self.enabled or max_tokens <= 0:
            return []
        query_words = {word.casefold() for word in _WORDS.findall(text)}
        path_values = [value.casefold() for value in (paths or [])]
        now = datetime.now(UTC)
        scored: builtins.list[tuple[float, MemoryRecord]] = []
        for record in self._load():
            if not record.enabled:
                continue
            words = {word.casefold() for word in _WORDS.findall(record.content)}
            overlap = len(query_words & words)
            path_score = sum(1 for path in path_values if path and path in record.content.casefold())
            kind_score = 1.5 if record.kind in {MemoryKind.CONSTRAINT, MemoryKind.COMMAND} else 0.5
            recency = 0.0
            if record.last_used_at:
                days = max(0, (now - record.last_used_at).days)
                recency = 1 / (1 + days)
            score = overlap * 2 + path_score * 3 + kind_score + recency + record.confidence
            if score > 1:
                scored.append((score, record))
        selected: builtins.list[MemoryRecord] = []
        used_tokens = 0
        for _, record in sorted(scored, key=lambda item: (-item[0], item[1].id)):
            cost = _token_count(record.content) + 8
            if used_tokens + cost > max_tokens:
                continue
            record.last_used_at = now
            selected.append(record)
            used_tokens += cost
            if len(selected) >= max_items:
                break
        if selected:
            all_records = self._load()
            used_ids = {record.id: record.last_used_at for record in selected}
            for record in all_records:
                if record.id in used_ids:
                    record.last_used_at = used_ids[record.id]
            self._save(all_records)
        return selected

    @staticmethod
    def format_for_prompt(records: builtins.list[MemoryRecord]) -> str:
        if not records:
            return ""
        lines = ["Approved project memories (treat as experience, not repository rules):"]
        lines.extend(f"- [{record.kind.value}] {record.content}" for record in records)
        return "\n".join(lines)
