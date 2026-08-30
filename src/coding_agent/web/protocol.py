from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from coding_agent.safety.approval import ApprovalDecision

PROTOCOL_VERSION: Literal[2] = 2
SESSION_PATTERN = r"^[0-9a-f]{24}$"


class RequestFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[2] = PROTOCOL_VERSION
    type: str
    request_id: str = Field(min_length=1, max_length=128)


class InitializeRequest(RequestFrame):
    type: Literal["initialize"]
    last_seq: int = Field(default=0, ge=0)


class SessionListRequest(RequestFrame):
    type: Literal["session.list"]


class SessionCreateRequest(RequestFrame):
    type: Literal["session.create"]


class SessionResumeRequest(RequestFrame):
    type: Literal["session.resume"]
    session_id: str = Field(pattern=SESSION_PATTERN)


class TurnStartRequest(RequestFrame):
    type: Literal["turn.start"]
    task: str = Field(min_length=1, max_length=100_000)


class TurnCancelRequest(RequestFrame):
    type: Literal["turn.cancel"]


class ApprovalResolveRequest(RequestFrame):
    type: Literal["approval.resolve"]
    approval_id: str = Field(min_length=1, max_length=128)
    decision: ApprovalDecision


class FilePreviewRequest(RequestFrame):
    type: Literal["file.preview"]
    path: str = Field(min_length=1, max_length=4096)


class ChangesListRequest(RequestFrame):
    type: Literal["changes.list"]


class ConfigGetRequest(RequestFrame):
    type: Literal["config.get"]


class RuntimeStatusRequest(RequestFrame):
    type: Literal["runtime.status"]


class StepsGetRequest(RequestFrame):
    type: Literal["steps.get"]


class StepsSetRequest(RequestFrame):
    type: Literal["steps.set"]
    value: int = Field(ge=12, le=100)


class StepsResetRequest(RequestFrame):
    type: Literal["steps.reset"]


class PermissionsGetRequest(RequestFrame):
    type: Literal["permissions.get"]


class PermissionsSetRequest(RequestFrame):
    type: Literal["permissions.set"]
    mode: Literal["prompt", "auto", "read-only"]


class PlanGetRequest(RequestFrame):
    type: Literal["plan.get"]


class CompletionQueryRequest(RequestFrame):
    type: Literal["completion.query"]
    text: str = Field(max_length=100_000)
    cursor: int = Field(ge=0, le=100_000)
    limit: int = Field(default=40, ge=1, le=100)


class ModelListRequest(RequestFrame):
    type: Literal["model.list"]


class ModelSelectRequest(RequestFrame):
    type: Literal["model.select"]
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    model_id: str | None = Field(default=None, min_length=1, max_length=256)


class ModelReloadRequest(RequestFrame):
    type: Literal["model.reload"]


class ModelProviderUpsertRequest(RequestFrame):
    type: Literal["model.provider.upsert"]
    provider: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    base_url: str = Field(min_length=8, max_length=2048)
    model: str = Field(min_length=1, max_length=256)
    compatibility: Literal["openai", "gemini"] = "openai"


class MemoryListRequest(RequestFrame):
    type: Literal["memory.list"]


class MemoryToggleRequest(RequestFrame):
    type: Literal["memory.toggle"]
    enabled: bool


class MemoryRememberRequest(RequestFrame):
    type: Literal["memory.remember"]
    content: str = Field(min_length=1, max_length=1000)


class MemoryForgetRequest(RequestFrame):
    type: Literal["memory.forget"]
    memory_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class MemoryClearRequest(RequestFrame):
    type: Literal["memory.clear"]
    confirm: Literal[True]


class SkillsListRequest(RequestFrame):
    type: Literal["skills.list"]


class SkillsToggleRequest(RequestFrame):
    type: Literal["skills.toggle"]
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    enabled: bool


class SkillsReloadRequest(RequestFrame):
    type: Literal["skills.reload"]


class ContextGetRequest(RequestFrame):
    type: Literal["context.get"]


class ContextCompactRequest(RequestFrame):
    type: Literal["context.compact"]


ClientRequest: TypeAlias = Annotated[
    InitializeRequest
    | SessionListRequest
    | SessionCreateRequest
    | SessionResumeRequest
    | TurnStartRequest
    | TurnCancelRequest
    | ApprovalResolveRequest
    | FilePreviewRequest
    | ChangesListRequest
    | ConfigGetRequest
    | RuntimeStatusRequest
    | StepsGetRequest
    | StepsSetRequest
    | StepsResetRequest
    | PermissionsGetRequest
    | PermissionsSetRequest
    | PlanGetRequest
    | CompletionQueryRequest
    | ModelListRequest
    | ModelSelectRequest
    | ModelReloadRequest
    | ModelProviderUpsertRequest
    | MemoryListRequest
    | MemoryToggleRequest
    | MemoryRememberRequest
    | MemoryForgetRequest
    | MemoryClearRequest
    | SkillsListRequest
    | SkillsToggleRequest
    | SkillsReloadRequest
    | ContextGetRequest
    | ContextCompactRequest,
    Field(discriminator="type"),
]

_CLIENT_REQUEST_ADAPTER: TypeAdapter[ClientRequest] = TypeAdapter(ClientRequest)


def parse_client_request(value: Any) -> ClientRequest:
    """Validate an untrusted renderer request against the closed protocol union."""

    return _CLIENT_REQUEST_ADAPTER.validate_python(value)


class ViewEventType(StrEnum):
    SNAPSHOT = "snapshot"
    TURN_STARTED = "turn.started"
    TURN_PROGRESS = "turn.progress"
    MESSAGE_DELTA = "message.delta"
    MESSAGE_FINAL = "message.final"
    ACTIVITY_UPSERT = "activity.upsert"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    PLAN_UPDATED = "plan.updated"
    CHANGE_RECORDED = "change.recorded"
    CONTEXT_UPDATED = "context.updated"
    TURN_FINISHED = "turn.finished"
    ERROR = "error"
    FILE_PREVIEWED = "file.previewed"
    CHANGES_UPDATED = "changes.updated"
    RUNTIME_UPDATED = "runtime.updated"
    COMMAND_COMPLETED = "command.completed"
    COMPLETION_UPDATED = "completion.updated"
    MODEL_CATALOG_UPDATED = "model.catalog.updated"
    MEMORY_UPDATED = "memory.updated"
    SKILLS_UPDATED = "skills.updated"
    CONTEXT_COMPACTED = "context.compacted"


class ViewEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[2] = PROTOCOL_VERSION
    type: ViewEventType
    seq: int = Field(ge=1)
    session_id: str = Field(pattern=SESSION_PATTERN)
    turn_id: str | None = Field(default=None, max_length=128)
    data: dict[str, Any] = Field(default_factory=dict)
