from __future__ import annotations

from coding_agent.change_ledger import CHANGE_RECORD_TYPE, restore_changes, serialize_change
from coding_agent.tools.base import AppliedChange


def test_created_directories_survive_change_ledger_round_trip() -> None:
    change = AppliedChange(
        id="change-1",
        path="algorithm_practice/tests/test_trap.py",
        kind="created",
        diff="+def test_trap(): pass\n",
        before_text=None,
        after_sha256="abc123",
        reversible=True,
        created_directories=["algorithm_practice", "algorithm_practice/tests"],
    )

    restored = restore_changes([{"type": CHANGE_RECORD_TYPE, "data": serialize_change(change)}])

    assert restored[0].created_directories == [
        "algorithm_practice",
        "algorithm_practice/tests",
    ]


def test_change_turn_id_survives_change_ledger_round_trip() -> None:
    """Dropping turn ownership would make focused manual verification run unrelated rules."""

    change = AppliedChange(
        id="change-turn",
        path="web/src/app.tsx",
        kind="modified",
        diff="-old\n+new\n",
        before_text="old\n",
        after_sha256="def456",
        turn_id="turn-web",
    )

    restored = restore_changes([{"type": CHANGE_RECORD_TYPE, "data": serialize_change(change)}])

    assert restored[0].turn_id == "turn-web"
