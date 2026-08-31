from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from coding_agent.workspace_settings import VerificationCheck

VERIFICATION_CONFIG_RECORD_TYPE = "verification_config"
VERIFICATION_RESULT_RECORD_TYPE = "verification_result"


class VerificationMode(StrEnum):
    OFF = "off"
    CHECKS = "checks"
    AGENT_TDD = "agent_tdd"


class VerificationProcedure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    instruction: str
    enabled: bool = True

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or len(normalized) > 1000:
            raise ValueError("verification procedure must contain 1 to 1000 characters")
        return normalized


class VerificationContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: VerificationMode = VerificationMode.OFF
    checks: list[VerificationCheck] = Field(default_factory=list, max_length=8)
    procedures: list[VerificationProcedure] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> VerificationContract:
        check_ids = [check.id for check in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("verification rule IDs must be unique within a session")
        procedure_ids = [procedure.id for procedure in self.procedures]
        if len(procedure_ids) != len(set(procedure_ids)):
            raise ValueError("verification procedure IDs must be unique within a session")
        return self

    @property
    def enabled(self) -> bool:
        return self.mode is not VerificationMode.OFF

    @property
    def agent_tdd(self) -> bool:
        return self.mode is VerificationMode.AGENT_TDD

    @property
    def commands(self) -> list[str]:
        return [check.command for check in self.checks if check.enabled]


VerificationStatus = Literal[
    "passed",
    "test_failed",
    "configuration_error",
    "approval_denied",
    "timed_out",
    "cancelled",
    "not_configured",
    "not_needed",
]


class VerificationResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str = Field(min_length=1, max_length=128)
    status: VerificationStatus
    command_count: int = Field(default=0, ge=0)
    check_id: str | None = None
    command: str | None = None
    cwd: str | None = None
    target_paths: list[str] = Field(default_factory=list)
    summary: str = ""
    queue_ms: int = Field(default=0, ge=0)
    approval_wait_ms: int = Field(default=0, ge=0)
    execution_ms: int = Field(default=0, ge=0)
    manual: bool = False


def restore_verification_contract(records: list[dict[str, Any]]) -> VerificationContract | None:
    for record in reversed(records):
        if record.get("type") != VERIFICATION_CONFIG_RECORD_TYPE:
            continue
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        try:
            return VerificationContract.model_validate(data)
        except (TypeError, ValueError):
            continue
    return None


def restore_verification_results(records: list[dict[str, Any]]) -> list[VerificationResultRecord]:
    restored: list[VerificationResultRecord] = []
    for record in records:
        if record.get("type") != VERIFICATION_RESULT_RECORD_TYPE:
            continue
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        try:
            restored.append(VerificationResultRecord.model_validate(data))
        except (TypeError, ValueError):
            continue
    return restored
