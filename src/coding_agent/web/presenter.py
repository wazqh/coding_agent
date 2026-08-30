from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from coding_agent.events import AgentEvent, AgentState, EventKind
from coding_agent.web.changes import summarize_diff
from coding_agent.web.protocol import ViewEvent, ViewEventType

_ROUTINE_TOOLS = {"read_file", "list_files", "search_text"}
_VALIDATION_COMMANDS = re.compile(
    r"(?:^|[;&|]\s*)(?:"
    r"(?:python\s+-m\s+)?(?:pytest|ruff|mypy|build)(?:\s|$)|"
    r"(?:npm|pnpm|yarn)\s+(?:test|run\s+(?:test|lint|typecheck|build))(?:\s|$)|"
    r"cargo\s+(?:test|check)(?:\s|$)|go\s+test(?:\s|$)|"
    r"(?:tox|nox)(?:\s|$)"
    r")",
    re.IGNORECASE,
)


@dataclass
class _RoutineActivity:
    activity_id: str
    count: int = 0
    pending: set[str] = field(default_factory=set)
    steps: list[dict[str, str]] = field(default_factory=list)
    call_indexes: dict[str, int] = field(default_factory=dict)


class AgentEventPresenter:
    """Convert controller events into stable, concise graphical timeline events."""

    def __init__(self, *, start_seq: int = 0) -> None:
        self._seq = start_seq
        self._call_activity: dict[str, str] = {}
        self._call_kind: dict[str, str] = {}
        self._call_arguments: dict[str, dict[str, Any]] = {}
        self._routine: dict[str, _RoutineActivity] = {}

    def _view(
        self,
        source: AgentEvent,
        kind: ViewEventType,
        data: dict[str, Any],
    ) -> ViewEvent:
        self._seq += 1
        return ViewEvent(
            type=kind,
            seq=self._seq,
            session_id=source.session_id,
            turn_id=source.turn_id,
            data=data,
        )

    def create_view(
        self,
        *,
        session_id: str,
        kind: ViewEventType,
        data: dict[str, Any],
        turn_id: str | None = None,
    ) -> ViewEvent:
        """Sequence a coordinator-owned event through the same event clock."""

        self._seq += 1
        return ViewEvent(
            type=kind,
            seq=self._seq,
            session_id=session_id,
            turn_id=turn_id,
            data=data,
        )

    def present(self, event: AgentEvent) -> list[ViewEvent]:
        if event.kind is EventKind.TEXT:
            return [
                self._view(
                    event, ViewEventType.MESSAGE_DELTA, {"delta": event.data.get("delta", "")}
                )
            ]
        if event.kind is EventKind.TOOL_CALL:
            if event.data.get("name") == "update_plan":
                return []
            return [self._present_tool_call(event)]
        if event.kind is EventKind.TOOL_RESULT:
            if event.data.get("name") == "update_plan":
                return []
            result = [self._present_tool_result(event)]
            change = self._present_change(event)
            if change is not None:
                result.append(change)
            return result
        if event.kind is EventKind.PLAN:
            return [
                self._view(event, ViewEventType.PLAN_UPDATED, {"plan": event.data.get("plan", [])})
            ]
        if event.kind is EventKind.APPROVAL:
            if "request" in event.data:
                return [self._view(event, ViewEventType.APPROVAL_REQUESTED, dict(event.data))]
            return [self._view(event, ViewEventType.APPROVAL_RESOLVED, dict(event.data))]
        if event.kind is EventKind.USAGE:
            prompt = int(event.data.get("prompt_tokens", 0))
            completion = int(event.data.get("completion_tokens", 0))
            total = int(event.data.get("total_tokens", prompt + completion))
            return [
                self._view(
                    event,
                    ViewEventType.CONTEXT_UPDATED,
                    {
                        "prompt_tokens": prompt,
                        "completion_tokens": completion,
                        "total_tokens": total,
                    },
                )
            ]
        if event.kind is EventKind.COMPACT:
            return [
                self._view(
                    event,
                    ViewEventType.CONTEXT_UPDATED,
                    {"action": "compacted", **event.data},
                )
            ]
        if event.kind is EventKind.DONE:
            status = event.state.value if event.state is not None else AgentState.COMPLETED.value
            return [
                self._view(
                    event,
                    ViewEventType.TURN_FINISHED,
                    {"status": status, **event.data},
                )
            ]
        if event.kind in {EventKind.ERROR, EventKind.WARNING}:
            severity = "warning" if event.kind is EventKind.WARNING else "error"
            return [self._view(event, ViewEventType.ERROR, {"severity": severity, **event.data})]
        if event.kind is EventKind.SESSION:
            return [self._view(event, ViewEventType.SNAPSHOT, dict(event.data))]
        if event.kind in {EventKind.MEMORY, EventKind.SKILL}:
            resource = "memory" if event.kind is EventKind.MEMORY else "skill"
            return [
                self._view(
                    event,
                    ViewEventType.ACTIVITY_UPSERT,
                    {
                        "activity_id": f"{resource}:{event.turn_id or event.event_id}",
                        "kind": resource,
                        "status": "completed",
                        **event.data,
                    },
                )
            ]
        if event.kind is EventKind.STATE:
            if event.state in {AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED}:
                return []
            data: dict[str, Any] = {
                "status": (
                    event.state.value if event.state is not None else AgentState.THINKING.value
                )
            }
            if isinstance(event.data.get("step"), int):
                data["step"] = event.data["step"]
            if isinstance(event.data.get("tool"), str):
                data["tool"] = event.data["tool"]
            return [self._view(event, ViewEventType.TURN_PROGRESS, data)]
        return []

    def _present_tool_call(self, event: AgentEvent) -> ViewEvent:
        call_id = str(event.data.get("id", event.event_id))
        name = str(event.data.get("name", "tool"))
        arguments = event.data.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        self._call_arguments[call_id] = dict(arguments)
        if name in _ROUTINE_TOOLS:
            turn_key = event.turn_id or event.session_id
            routine = self._routine.setdefault(
                turn_key,
                _RoutineActivity(activity_id=f"routine:{turn_key}"),
            )
            routine.count += 1
            routine.pending.add(call_id)
            routine.call_indexes[call_id] = len(routine.steps)
            routine.steps.append(
                {
                    "name": name,
                    "subject": self._tool_subject(name, arguments),
                    "status": "running",
                    "summary": "",
                }
            )
            activity_id = routine.activity_id
            self._call_activity[call_id] = activity_id
            return self._view(
                event,
                ViewEventType.ACTIVITY_UPSERT,
                {
                    "activity_id": activity_id,
                    "kind": "workspace_check",
                    "title": "检查工作区",
                    "status": "running",
                    "count": routine.count,
                    "summary": self._tool_subject(name, arguments),
                    "detail": {
                        "steps": [dict(step) for step in routine.steps],
                        "raw": {"name": name, "arguments": arguments},
                    },
                },
            )

        activity_id = f"tool:{call_id}"
        self._call_activity[call_id] = activity_id
        activity_kind = self._activity_kind(name, arguments)
        self._call_kind[call_id] = activity_kind
        return self._view(
            event,
            ViewEventType.ACTIVITY_UPSERT,
            {
                "activity_id": activity_id,
                "kind": activity_kind,
                "title": self._activity_title(name, activity_kind),
                "status": "running",
                "summary": self._tool_subject(name, arguments),
                "detail": {"name": name, "arguments": arguments},
            },
        )

    def _present_tool_result(self, event: AgentEvent) -> ViewEvent:
        call_id = str(event.data.get("id", event.event_id))
        name = str(event.data.get("name", "tool"))
        result = event.data.get("result", {})
        if not isinstance(result, dict):
            result = {}
        if name == "run_command":
            arguments = self._call_arguments.get(call_id, {})
            command = arguments.get("command")
            if isinstance(command, str):
                result = dict(result)
                result_data = result.get("data", {})
                result_data = dict(result_data) if isinstance(result_data, dict) else {}
                result_data.setdefault("command", command)
                result["data"] = result_data
        activity_id = self._call_activity.get(call_id, f"tool:{call_id}")
        status = "completed" if result.get("ok") else "failed"
        count: int | None = None
        if name in _ROUTINE_TOOLS:
            turn_key = event.turn_id or event.session_id
            routine = self._routine.get(turn_key)
            if routine is not None:
                routine.pending.discard(call_id)
                count = routine.count
                step_index = routine.call_indexes.get(call_id)
                if step_index is not None:
                    routine.steps[step_index]["status"] = status
                    routine.steps[step_index]["summary"] = str(result.get("summary", ""))
                if routine.pending and status == "completed":
                    status = "running"
        activity_kind = (
            "workspace_check" if name in _ROUTINE_TOOLS else self._call_kind.get(call_id, "tool")
        )
        data: dict[str, Any] = {
            "activity_id": activity_id,
            "kind": activity_kind,
            "title": (
                "检查工作区"
                if name in _ROUTINE_TOOLS
                else self._activity_title(name, activity_kind)
            ),
            "status": status,
            "summary": str(result.get("summary", "操作已完成")),
            "detail": (
                {
                    "steps": [dict(step) for step in routine.steps],
                    "raw": result,
                }
                if name in _ROUTINE_TOOLS and routine is not None
                else result
            ),
        }
        if count is not None:
            data["count"] = count
        return self._view(event, ViewEventType.ACTIVITY_UPSERT, data)

    def _present_change(self, event: AgentEvent) -> ViewEvent | None:
        result = event.data.get("result", {})
        if not isinstance(result, dict) or result.get("ok") is not True:
            return None
        data = result.get("data", {})
        if not isinstance(data, dict):
            return None
        change_id = data.get("change_id")
        kind = data.get("change_kind")
        path = data.get("path")
        diff = data.get("diff")
        if not (
            isinstance(change_id, str)
            and isinstance(kind, str)
            and isinstance(path, str)
            and isinstance(diff, str)
        ):
            return None
        if kind not in {"created", "modified"}:
            return None
        summary = summarize_diff(
            change_id=change_id,
            path=path,
            kind=kind,
            diff=diff,
        )
        summary["reversible"] = data.get("reversible") is not False and not bool(
            result.get("truncated")
        )
        return self._view(
            event,
            ViewEventType.CHANGE_RECORDED,
            summary,
        )

    @staticmethod
    def _activity_kind(name: str, arguments: dict[str, Any]) -> str:
        if name in {"apply_patch", "edit_file", "write_file", "replace_text"}:
            return "file_change"
        if name != "run_command":
            return "tool"
        command = str(arguments.get("command", "")).strip()
        return "validation" if _VALIDATION_COMMANDS.search(command) else "command"

    @staticmethod
    def _activity_title(name: str, activity_kind: str) -> str:
        if activity_kind == "validation":
            return "运行验证"
        if activity_kind == "command":
            return "运行命令"
        if activity_kind == "file_change":
            return "修改文件"
        return name

    @staticmethod
    def _tool_subject(name: str, arguments: dict[str, Any]) -> str:
        if name == "read_file":
            return f"读取 {arguments.get('path', '文件')}"
        if name == "list_files":
            return f"浏览 {arguments.get('path', '.')}"
        if name == "search_text":
            return f"搜索 {arguments.get('query', '文本')}"
        if name == "run_command":
            return str(arguments.get("command", name))
        if name in {"apply_patch", "edit_file", "write_file", "replace_text"}:
            return str(arguments.get("path", arguments.get("file", "工作区文件")))
        return name

    def present_history(
        self,
        session_id: str,
        records: list[dict[str, Any]],
    ) -> list[ViewEvent]:
        """Restore final messages and semantic receipts without replaying side effects."""

        result: list[ViewEvent] = []
        for record in records:
            record_type = record.get("type")
            if record_type == "event":
                try:
                    event = AgentEvent.model_validate(record.get("data"))
                except ValueError:
                    continue
                if event.kind not in {
                    EventKind.PLAN,
                    EventKind.TOOL_CALL,
                    EventKind.TOOL_RESULT,
                    EventKind.ERROR,
                    EventKind.WARNING,
                    EventKind.MEMORY,
                    EventKind.SKILL,
                    EventKind.DONE,
                }:
                    continue
                result.extend(self.present(event))
                continue
            if record_type != "message":
                continue
            message = record.get("data")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            self._seq += 1
            result.append(
                ViewEvent(
                    type=ViewEventType.MESSAGE_FINAL,
                    seq=self._seq,
                    session_id=session_id,
                    data={"role": role, "content": content},
                )
            )
        return result
