from __future__ import annotations

from pathlib import Path

from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.safety.paths import WorkspacePaths
from coding_agent.skills import SkillRegistry
from coding_agent.tools.base import ToolContext, WorkingState
from coding_agent.tools.registry import default_registry


def test_skill_tools(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\nUse this.\n", encoding="utf-8"
    )
    (skill_dir / "note.txt").write_text("note", encoding="utf-8")
    skills = SkillRegistry(workspace=tmp_path, user_root=tmp_path / "none")
    skills.discover(include_repo=True)
    working = WorkingState()
    ctx = ToolContext(
        workspace=WorkspacePaths(tmp_path),
        approval=ApprovalPolicy("auto"),
        session_id="a" * 24,
        turn_id="turn",
        working=working,
        skills=skills,
    )
    registry = default_registry()
    inactive = registry.execute("read_skill_resource", {"name": "demo", "path": "note.txt"}, ctx)
    assert inactive.code == "SKILL_ERROR"
    active = registry.execute("activate_skill", {"name": "demo"}, ctx)
    assert active.ok and "demo" in working.active_skills
    resource = registry.execute("read_skill_resource", {"name": "demo", "path": "note.txt"}, ctx)
    assert resource.ok and resource.data["content"] == "note"
