from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentState(StrEnum):
    IDLE = "idle"
    THINKING = "thinking"
    PLANNING = "planning"
    TOOL_PENDING = "tool_pending"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    OBSERVING = "observing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventKind(StrEnum):
    STATE = "state"
    TEXT = "text"
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    APPROVAL = "approval"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    WARNING = "warning"
    USAGE = "usage"
    COMPACT = "compact"
    MEMORY = "memory"
    SKILL = "skill"
    VERIFICATION = "verification"
    SESSION = "session"
    DONE = "done"


class ToolResult(BaseModel):
    """The only result shape tools are allowed to return."""

    ok: bool
    code: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
    truncated: bool = False


class AgentEvent(BaseModel):
    kind: EventKind
    session_id: str
    turn_id: str | None = None
    state: AgentState | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]
    thought_signature: str | None = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelStreamEvent(BaseModel):
    type: Literal["text_delta", "tool_calls", "usage", "done", "error"]
    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage | None = None
    finish_reason: str | None = None
    error: str | None = None
