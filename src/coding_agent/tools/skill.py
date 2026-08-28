from __future__ import annotations

from pydantic import BaseModel, Field

from coding_agent.events import EventKind, ToolResult
from coding_agent.skills import SkillError
from coding_agent.tools.base import Tool, ToolContext


class ActivateSkillArgs(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ActivateSkillTool(Tool):
    name = "activate_skill"
    description = "Activate a discovered skill and load its SKILL.md instructions on demand."
    args_model = ActivateSkillArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = ActivateSkillArgs.model_validate(args)
        if context.skills is None:
            return ToolResult(ok=False, code="SKILLS_UNAVAILABLE", summary="skills are unavailable")
        try:
            content = context.skills.activate(values.name)
        except SkillError as exc:
            return ToolResult(ok=False, code="SKILL_ERROR", summary=str(exc))
        if values.name not in context.working.active_skills:
            context.working.active_skills.append(values.name)
        context.emit(EventKind.SKILL, {"name": values.name, "action": "activated"})
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"activated skill {values.name}",
            data={"name": values.name, "instructions": content},
        )


class ReadSkillResourceArgs(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=500)


class ReadSkillResourceTool(Tool):
    name = "read_skill_resource"
    description = "Read a UTF-8 resource inside an already active skill directory."
    args_model = ReadSkillResourceArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = ReadSkillResourceArgs.model_validate(args)
        if context.skills is None:
            return ToolResult(ok=False, code="SKILLS_UNAVAILABLE", summary="skills are unavailable")
        try:
            content = context.skills.read_resource(values.name, values.path)
        except (SkillError, OSError) as exc:
            return ToolResult(ok=False, code="SKILL_ERROR", summary=str(exc))
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"read {values.name}/{values.path}",
            data={"name": values.name, "path": values.path, "content": content},
        )

