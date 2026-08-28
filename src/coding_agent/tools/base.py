from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel, Field

from coding_agent.events import AgentEvent, AgentState, EventKind, ToolResult
from coding_agent.safety.approval import ApprovalDecision, ApprovalPolicy, ApprovalRequest
from coding_agent.safety.paths import WorkspacePaths

if TYPE_CHECKING:
    from coding_agent.skills import SkillRegistry


class WorkingState(BaseModel):
    goal: str = ""
    plan: list[dict[str, str]] = Field(default_factory=list)
    recent_calls: list[dict[str, Any]] = Field(default_factory=list)
    modified_files: dict[str, str] = Field(default_factory=dict)
    active_skills: list[str] = Field(default_factory=list)
    diffs: list[str] = Field(default_factory=list)


EventSink = Callable[[AgentEvent], None]


class ToolContext:
    def __init__(
        self,
        *,
        workspace: WorkspacePaths,
        approval: ApprovalPolicy,
        session_id: str,
        turn_id: str,
        working: WorkingState,
        event_sink: EventSink | None = None,
        command_timeout: int = 120,
        skills: SkillRegistry | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> None:
        self.workspace = workspace
        self.approval = approval
        self.session_id = session_id
        self.turn_id = turn_id
        self.working = working
        self.event_sink = event_sink
        self.command_timeout = command_timeout
        self.skills = skills
        self.cancel_requested = cancel_requested or (lambda: False)

    def emit(
        self,
        kind: EventKind,
        data: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> None:
        if self.event_sink:
            self.event_sink(
                AgentEvent(
                    kind=kind,
                    session_id=self.session_id,
                    turn_id=self.turn_id,
                    state=state,
                    data=data,
                )
            )

    def approve(self, request: ApprovalRequest) -> bool:
        if self.cancel_requested():
            return False
        self.emit(
            EventKind.APPROVAL,
            {"request": request.model_dump(mode="json")},
            state=AgentState.AWAITING_APPROVAL,
        )
        decision = self.approval.decide(request)
        self.emit(
            EventKind.APPROVAL,
            {"decision": decision.value, "subject": request.subject},
            state=AgentState.EXECUTING,
        )
        return decision is not ApprovalDecision.DENY and not self.cancel_requested()


class EmptyArgs(BaseModel):
    pass


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[BaseModel]] = EmptyArgs

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    @abstractmethod
    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        raise NotImplementedError
