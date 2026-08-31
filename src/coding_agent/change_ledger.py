from __future__ import annotations

from typing import Any, Literal

from coding_agent.tools.base import AppliedChange

CHANGE_RECORD_TYPE = "change"
CHANGE_REVIEW_TYPE = "change_review"
MAX_PERSISTED_BACKUP_CHARS = 256 * 1024

ReviewStatus = Literal["pending", "accepted", "conflicted"]


def serialize_change(change: AppliedChange) -> dict[str, Any]:
    """Return a bounded durable representation of an applied file change."""

    before_text = change.before_text
    reversible = change.reversible
    if before_text is not None and len(before_text) > MAX_PERSISTED_BACKUP_CHARS:
        before_text = None
        reversible = False
    return {
        "id": change.id,
        "path": change.path,
        "kind": change.kind,
        "diff": change.diff,
        "before_text": before_text,
        "after_sha256": change.after_sha256,
        "reversible": reversible,
        "review_status": change.review_status,
        "turn_id": change.turn_id,
        "created_directories": change.created_directories,
    }


def review_record(change_id: str, status: ReviewStatus | Literal["reverted"]) -> dict[str, str]:
    return {"change_id": change_id, "status": status}


def restore_changes(records: list[dict[str, Any]]) -> list[AppliedChange]:
    """Replay append-only change and review records into the current visible ledger."""

    changes: dict[str, AppliedChange] = {}
    order: list[str] = []
    for record in records:
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        if record.get("type") == CHANGE_RECORD_TYPE:
            try:
                change = AppliedChange.model_validate(data)
            except (TypeError, ValueError):
                continue
            if change.id not in changes:
                order.append(change.id)
            changes[change.id] = change
            continue
        if record.get("type") != CHANGE_REVIEW_TYPE:
            continue
        change_id = data.get("change_id")
        status = data.get("status")
        if not isinstance(change_id, str) or change_id not in changes:
            continue
        if status == "reverted":
            changes.pop(change_id, None)
            continue
        if status in {"pending", "accepted", "conflicted"}:
            changes[change_id].review_status = status
    return [changes[change_id] for change_id in order if change_id in changes]
