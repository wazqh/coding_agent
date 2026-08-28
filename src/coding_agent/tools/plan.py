from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from coding_agent.events import EventKind, ToolResult
from coding_agent.tools.base import Tool, ToolContext


class PlanStep(BaseModel):
    step: str = Field(min_length=1, max_length=300)
    status: Literal["pending", "in_progress", "completed"]


class UpdatePlanArgs(BaseModel):
    explanation: str | None = Field(default=None, max_length=1000)
    plan: list[PlanStep] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def one_active_step(self) -> UpdatePlanArgs:
        if sum(item.status == "in_progress" for item in self.plan) > 1:
            raise ValueError("at most one plan step may be in progress")
        return self


class UpdatePlanTool(Tool):
    name = "update_plan"
    description = "Create or update the visible task plan. Keep at most one step in progress."
    args_model = UpdatePlanArgs

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = UpdatePlanArgs.model_validate(args)
        plan = [item.model_dump() for item in values.plan]
        context.working.plan = plan
        context.emit(EventKind.PLAN, {"plan": plan, "explanation": values.explanation})
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"plan updated with {len(plan)} steps",
            data={"plan": plan},
        )
