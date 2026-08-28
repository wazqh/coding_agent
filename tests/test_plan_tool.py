from __future__ import annotations

from pathlib import Path

from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.safety.paths import WorkspacePaths
from coding_agent.tools.base import ToolContext, WorkingState
from coding_agent.tools.registry import default_registry


def test_plan_rejects_multiple_active_steps_and_updates_state(tmp_path: Path) -> None:
    working = WorkingState()
    context = ToolContext(
        workspace=WorkspacePaths(tmp_path),
        approval=ApprovalPolicy("auto"),
        session_id="a" * 24,
        turn_id="turn",
        working=working,
    )
    registry = default_registry()
    invalid = registry.execute(
        "update_plan",
        {
            "plan": [
                {"step": "one", "status": "in_progress"},
                {"step": "two", "status": "in_progress"},
            ]
        },
        context,
    )
    assert invalid.code == "INVALID_ARGUMENTS"
    valid = registry.execute(
        "update_plan",
        {"plan": [{"step": "one", "status": "completed"}]},
        context,
    )
    assert valid.ok and working.plan[0]["status"] == "completed"
