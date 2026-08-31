from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

from coding_agent.branding import PRODUCT_NAME
from coding_agent.change_ledger import CHANGE_RECORD_TYPE, restore_changes, serialize_change
from coding_agent.config import Settings
from coding_agent.context import ContextManager, estimate_request_tokens
from coding_agent.events import AgentEvent, AgentState, EventKind, ToolCall
from coding_agent.memory import MemoryStore
from coding_agent.model_client import ModelClient
from coding_agent.model_runtime import ModelManager
from coding_agent.project import project_id
from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.safety.paths import WorkspacePaths
from coding_agent.session import SessionError, SessionStore
from coding_agent.skills import SkillError, SkillRegistry
from coding_agent.tokens import count_tokens
from coding_agent.tools.base import EventSink, ToolContext, WorkingState
from coding_agent.tools.registry import ToolRegistry


@dataclass(frozen=True)
class RunResult:
    status: AgentState
    exit_code: int
    session_id: str
    content: str
    tool_steps: int
    reason: str


class AgentController:
    def __init__(
        self,
        *,
        settings: Settings,
        model: ModelClient,
        tools: ToolRegistry,
        sessions: SessionStore,
        approval: ApprovalPolicy,
        memory: MemoryStore | None = None,
        skills: SkillRegistry | None = None,
        agents_instructions: str = "",
        session_id: str | None = None,
        event_sink: EventSink | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        model_manager: ModelManager | None = None,
        verification_commands: list[str] | tuple[str, ...] = (),
    ) -> None:
        self.settings = settings
        self.model = model
        self.model_manager = model_manager
        self.verification_commands = tuple(verification_commands)
        self.tools = tools
        self.sessions = sessions
        self.approval = approval
        self.memory = memory
        self.skills = skills
        self.agents_instructions = agents_instructions
        self.session_id = session_id or sessions.create(
            {
                "workspace": str(settings.cwd.resolve()),
                "project_id": project_id(settings.cwd),
                "model": settings.model.name,
            }
        )
        self.event_sink = event_sink
        self.monotonic = monotonic
        self.working = WorkingState()
        self.context = ContextManager(context_window=settings.agent.context_window)
        self.conversation: list[dict[str, Any]] = []
        self._last_system_prompt = ""
        if session_id is not None:
            self._restore(session_id)
        self.last_context_tokens = estimate_request_tokens(
            self._messages_for_model(self.conversation), self.tools.schemas()
        )

    def context_breakdown(self) -> dict[str, int]:
        """Return an approximate token split without exposing request contents."""

        system = count_tokens(self._last_system_prompt) if self._last_system_prompt else 0
        history = count_tokens(json.dumps(self.conversation, ensure_ascii=False))
        tool_schemas = count_tokens(json.dumps(self.tools.schemas(), ensure_ascii=False))
        measured = system + history + tool_schemas
        return {
            "system_and_project": system,
            "conversation_and_results": history,
            "tool_schemas": tool_schemas,
            "other": max(0, self.last_context_tokens - measured),
        }

    def _restore(self, session_id: str) -> None:
        records = self.sessions.replay(session_id)
        metadata: dict[str, Any] = next(
            (record["data"] for record in records if record["type"] == "session"), {}
        )
        recorded_workspace = metadata.get("workspace")
        if (
            recorded_workspace
            and Path(str(recorded_workspace)).resolve() != self.settings.cwd.resolve()
        ):
            raise SessionError("session belongs to a different workspace")
        self.conversation = []
        self.working.changes = restore_changes(records)
        self.working.diffs = [change.diff for change in self.working.changes]
        self.working.modified_files = {
            change.path: change.after_sha256 for change in self.working.changes
        }
        for record in records:
            if record["type"] == "message" and isinstance(record["data"], dict):
                self.conversation.append(record["data"])
                continue
            if record["type"] == "compact":
                snapshot = record["data"].get("conversation")
                if isinstance(snapshot, list) and all(
                    isinstance(message, dict) for message in snapshot
                ):
                    self.conversation = [dict(message) for message in snapshot]
                continue
            if record["type"] != "event":
                continue
            data = record["data"]
            if data.get("kind") == EventKind.PLAN.value:
                self.working.plan = data.get("data", {}).get("plan", [])
            elif data.get("kind") == EventKind.SKILL.value and self.skills is not None:
                name = data.get("data", {}).get("name")
                if not isinstance(name, str):
                    continue
                action = data.get("data", {}).get("action", "activated")
                if action in {"enabled", "disabled"}:
                    try:
                        self.skills.set_enabled(name, action == "enabled")
                    except SkillError:
                        continue
                    if action == "disabled" and name in self.working.active_skills:
                        self.working.active_skills.remove(name)
                    continue
                try:
                    self.skills.activate(name)
                except SkillError:
                    continue
                if name not in self.working.active_skills:
                    self.working.active_skills.append(name)

    def set_skill_enabled(self, name: str, enabled: bool) -> None:
        """Update and persist a session-scoped skill availability choice."""

        if self.skills is None:
            raise SkillError("skills are unavailable")
        self.skills.set_enabled(name, enabled)
        if not enabled and name in self.working.active_skills:
            self.working.active_skills.remove(name)
        event = AgentEvent(
            kind=EventKind.SKILL,
            session_id=self.session_id,
            data={"name": name, "action": "enabled" if enabled else "disabled"},
        )
        self.sessions.append(self.session_id, "event", event.model_dump(mode="json"))

    def _emit(
        self,
        kind: EventKind,
        *,
        turn_id: str | None,
        state: AgentState | None = None,
        data: dict[str, Any] | None = None,
    ) -> AgentEvent:
        event = AgentEvent(
            kind=kind,
            session_id=self.session_id,
            turn_id=turn_id,
            state=state,
            data=data or {},
        )
        self.sessions.append(self.session_id, "event", event.model_dump(mode="json"))
        if self.event_sink:
            self.event_sink(event)
        return event

    def _set_state(self, state: AgentState, turn_id: str, **data: Any) -> None:
        self._emit(EventKind.STATE, turn_id=turn_id, state=state, data=data)

    def _append_message(self, message: dict[str, Any]) -> None:
        self.conversation.append(message)
        self.sessions.append_message(self.session_id, message)

    def _system_prompt(
        self,
        *,
        memory_text: str,
        explicit_skills: list[str],
        turn_id: str,
    ) -> str:
        sections = [
            (
                f"You are {PRODUCT_NAME}, a local coding agent. Complete the user's task "
                "using the provided local tools."
            ),
            (
                "Never claim a tool ran when it did not. Read files before editing; use returned "
                "SHA-256 values for edits and overwrites. Treat tool failures as observations and "
                "correct the plan or arguments. Do not reveal hidden chain-of-thought; communicate "
                "only concise plans, actions, results, and relevant rationale."
            ),
            (
                "Whenever you create or update the visible plan with update_plan, update it after "
                "each meaningful phase. Before your final response, call update_plan again so "
                "completed work is marked completed and remaining work stays accurately pending. "
                "Never mark unfinished work complete."
            ),
            f"Workspace boundary: {self.settings.cwd}",
        ]
        if self.agents_instructions:
            sections.append("Trusted repository instructions:\n" + self.agents_instructions)
        if memory_text:
            sections.append(memory_text)
        if self.skills is not None:
            catalog = self.skills.catalog() if self.settings.skills.implicit_activation else []
            if catalog:
                compact_catalog = [
                    {
                        "name": item["name"],
                        "description": item["description"],
                        "source": item["source"],
                    }
                    for item in catalog
                    if item["enabled"]
                ]
                sections.append(
                    "Available skills (activate only when relevant):\n"
                    + json.dumps(compact_catalog, ensure_ascii=False)
                )
            requested = list(dict.fromkeys([*sorted(self.skills.active), *explicit_skills]))
            for name in requested:
                try:
                    content = self.skills.activate(name)
                except SkillError as exc:
                    sections.append(f"Requested skill {name!r} could not be activated: {exc}")
                    continue
                if name not in self.working.active_skills:
                    self.working.active_skills.append(name)
                if name in explicit_skills:
                    self._emit(
                        EventKind.SKILL,
                        turn_id=turn_id,
                        data={"name": name, "action": "activated", "source": "explicit"},
                    )
                sections.append(f"Active skill {name}:\n{content}")
        return "\n\n".join(sections)

    @staticmethod
    def _explicit_skills(user_input: str) -> list[str]:
        return list(dict.fromkeys(re.findall(r"(?<!\w)\$([a-z0-9][a-z0-9_-]{0,63})", user_input)))

    def _tool_context(self, turn_id: str, cancel_event: Event | None = None) -> ToolContext:
        def tool_sink(event: AgentEvent) -> None:
            self.sessions.append(self.session_id, "event", event.model_dump(mode="json"))
            if self.event_sink:
                self.event_sink(event)

        return ToolContext(
            workspace=WorkspacePaths(self.settings.cwd),
            approval=self.approval,
            session_id=self.session_id,
            turn_id=turn_id,
            working=self.working,
            event_sink=tool_sink,
            command_timeout=self.settings.agent.command_timeout,
            skills=self.skills,
            cancel_requested=cancel_event.is_set if cancel_event is not None else None,
        )

    def manual_compact(self) -> str:
        compacted, summary = self.context.compact(self.conversation, self.working)
        if summary:
            self.conversation = compacted
            self.sessions.append(
                self.session_id,
                "compact",
                {
                    "summary": summary,
                    "manual": True,
                    "conversation": self.conversation,
                },
            )
            request_messages = self._messages_for_model(
                [
                    *(
                        [{"role": "system", "content": self._last_system_prompt}]
                        if self._last_system_prompt
                        else []
                    ),
                    *self.conversation,
                ]
            )
            self.last_context_tokens = estimate_request_tokens(
                request_messages, self.tools.schemas()
            )
        return summary

    def _append_unexecuted_tools(
        self,
        calls: list[ToolCall],
        start: int,
        *,
        code: str,
        summary: str,
    ) -> None:
        for skipped in calls[start:]:
            self._append_message(
                {
                    "role": "tool",
                    "tool_call_id": skipped.id,
                    "name": skipped.name,
                    "content": json.dumps(
                        {
                            "ok": False,
                            "code": code,
                            "summary": summary,
                            "data": {},
                            "retryable": False,
                            "truncated": False,
                        }
                    ),
                }
            )

    @staticmethod
    def _messages_for_model(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Coalesce adjacent user turns for strict OpenAI-compatible providers.

        Cancelled turns can leave adjacent user records, old compact snapshots can begin
        inside a tool chain, and a compact summary sits beside the current system prompt.
        Repair those request-only boundaries without rewriting durable session history.
        """

        prepared: list[dict[str, Any]] = []
        for message in messages:
            current = dict(message)
            role = current.get("role")
            if role in {"system", "user"} and prepared and prepared[-1].get("role") == role:
                previous = prepared[-1]
                previous_content = previous.get("content")
                current_content = current.get("content")
                if isinstance(previous_content, list) and isinstance(current_content, list):
                    previous["content"] = [*previous_content, *current_content]
                else:
                    parts = [
                        str(content)
                        for content in (previous_content, current_content)
                        if content is not None and content != ""
                    ]
                    previous["content"] = "\n\n".join(parts)
                continue
            prepared.append(current)

        system_count = 0
        while system_count < len(prepared) and prepared[system_count].get("role") == "system":
            system_count += 1
        first_user = next(
            (
                index
                for index in range(system_count, len(prepared))
                if prepared[index].get("role") == "user"
            ),
            len(prepared),
        )
        if first_user > system_count:
            prepared = [*prepared[:system_count], *prepared[first_user:]]
        return prepared

    def run_turn(self, user_input: str, *, cancel_event: Event | None = None) -> RunResult:
        turn_id = uuid4().hex[:16]
        started = self.monotonic()
        self.working.goal = user_input
        explicit_skills = self._explicit_skills(user_input)
        memory_text = ""
        if self.memory is not None:
            paths = re.findall(r"(?<!\w)@([^\s]+)", user_input)
            memories = self.memory.query(
                user_input,
                paths=paths,
                max_tokens=self.settings.memory.max_injected_tokens,
            )
            memory_text = self.memory.format_for_prompt(memories)
        system_prompt = self._system_prompt(
            memory_text=memory_text,
            explicit_skills=explicit_skills,
            turn_id=turn_id,
        )
        self._last_system_prompt = system_prompt
        tool_schemas = self.tools.schemas()
        prospective_request = self._messages_for_model(
            [
                {"role": "system", "content": system_prompt},
                *self.conversation,
                {"role": "user", "content": user_input},
            ]
        )
        self.last_context_tokens = estimate_request_tokens(prospective_request, tool_schemas)
        if self.context.should_compact(prospective_request, tool_schemas):
            before = self.last_context_tokens
            compacted, summary = self.context.compact(self.conversation, self.working)
            if summary:
                self.conversation = compacted
                self.sessions.append(
                    self.session_id,
                    "compact",
                    {
                        "summary": summary,
                        "manual": False,
                        "tokens_before": before,
                        "conversation": self.conversation,
                    },
                )
                self._emit(
                    EventKind.COMPACT,
                    turn_id=turn_id,
                    data={"tokens_before": before, "summary": summary},
                )
        self._append_message({"role": "user", "content": user_input})
        initial_change_ids = {change.id for change in self.working.changes}
        steps = 0
        last_text = ""
        failed_signature: str | None = None
        failed_count = 0
        verification_failures = 0

        try:
            while steps < self.settings.agent.max_steps:
                if cancel_event is not None and cancel_event.is_set():
                    return self._finish(
                        AgentState.CANCELLED, turn_id, last_text, steps, "cancelled by Esc", 130
                    )
                if self.monotonic() - started >= self.settings.agent.max_seconds:
                    return self._finish(
                        AgentState.FAILED,
                        turn_id,
                        last_text,
                        steps,
                        "turn time budget exhausted",
                    )
                tool_schemas = self.tools.schemas()
                request_messages = self._messages_for_model(
                    [
                        {"role": "system", "content": system_prompt},
                        *self.conversation,
                    ]
                )
                self.last_context_tokens = estimate_request_tokens(request_messages, tool_schemas)
                self._set_state(AgentState.THINKING, turn_id, step=steps)
                content_parts: list[str] = []
                tool_calls: list[ToolCall] = []
                model_error: str | None = None
                for event in self.model.stream(request_messages, tool_schemas):
                    if cancel_event is not None and cancel_event.is_set():
                        return self._finish(
                            AgentState.CANCELLED,
                            turn_id,
                            last_text,
                            steps,
                            "cancelled by Esc",
                            130,
                        )
                    if event.type == "text_delta" and event.text:
                        content_parts.append(event.text)
                        self._emit(EventKind.TEXT, turn_id=turn_id, data={"delta": event.text})
                    elif event.type == "tool_calls":
                        tool_calls = event.tool_calls
                    elif event.type == "usage" and event.usage:
                        self._emit(
                            EventKind.USAGE,
                            turn_id=turn_id,
                            data=event.usage.model_dump(),
                        )
                    elif event.type == "error":
                        model_error = event.error or "unknown model error"
                if cancel_event is not None and cancel_event.is_set():
                    return self._finish(
                        AgentState.CANCELLED,
                        turn_id,
                        last_text,
                        steps,
                        "cancelled by Esc",
                        130,
                    )
                content = "".join(content_parts)
                if content:
                    last_text = content
                if model_error:
                    self._emit(EventKind.ERROR, turn_id=turn_id, data={"message": model_error})
                    return self._finish(
                        AgentState.FAILED, turn_id, last_text, steps, f"model error: {model_error}"
                    )
                assistant: dict[str, Any] = {"role": "assistant", "content": content or None}
                if tool_calls:
                    assistant["tool_calls"] = []
                    for call in tool_calls:
                        call_payload: dict[str, Any] = {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                        if call.thought_signature:
                            call_payload["extra_content"] = {
                                "google": {"thought_signature": call.thought_signature}
                            }
                        assistant["tool_calls"].append(call_payload)
                if not tool_calls:
                    if not content.strip():
                        self._append_message(assistant)
                        return self._finish(
                            AgentState.FAILED,
                            turn_id,
                            content,
                            steps,
                            "model returned neither text nor tool calls",
                        )
                    changed_this_turn = any(
                        change.id not in initial_change_ids for change in self.working.changes
                    )
                    verification_failed = False
                    if changed_this_turn and self.verification_commands:
                        context = self._tool_context(turn_id, cancel_event)
                        for command in self.verification_commands:
                            if steps >= self.settings.agent.max_steps:
                                self._append_message(assistant)
                                return self._finish(
                                    AgentState.FAILED,
                                    turn_id,
                                    content,
                                    steps,
                                    "verification could not run within the tool step budget",
                                )
                            operation_id = f"verification-{uuid4().hex[:16]}"
                            arguments = {"command": command}
                            self._append_message(
                                {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": operation_id,
                                            "type": "function",
                                            "function": {
                                                "name": "run_command",
                                                "arguments": json.dumps(
                                                    arguments,
                                                    ensure_ascii=False,
                                                ),
                                            },
                                        }
                                    ],
                                }
                            )
                            steps += 1
                            self._set_state(
                                AgentState.TOOL_PENDING,
                                turn_id,
                                tool="run_command",
                                step=steps,
                            )
                            self._emit(
                                EventKind.TOOL_CALL,
                                turn_id=turn_id,
                                data={
                                    "id": operation_id,
                                    "name": "run_command",
                                    "arguments": arguments,
                                    "verification": True,
                                },
                            )
                            self._set_state(
                                AgentState.EXECUTING,
                                turn_id,
                                tool="run_command",
                                step=steps,
                            )
                            context.operation_id = operation_id
                            result = self.tools.execute("run_command", arguments, context)
                            self._append_message(
                                {
                                    "role": "tool",
                                    "tool_call_id": operation_id,
                                    "name": "run_command",
                                    "content": result.model_dump_json(),
                                }
                            )
                            self._set_state(
                                AgentState.OBSERVING,
                                turn_id,
                                tool="run_command",
                                step=steps,
                            )
                            self._emit(
                                EventKind.TOOL_RESULT,
                                turn_id=turn_id,
                                data={
                                    "id": operation_id,
                                    "name": "run_command",
                                    "result": result.model_dump(),
                                    "verification": True,
                                },
                            )
                            if cancel_event is not None and cancel_event.is_set():
                                return self._finish(
                                    AgentState.CANCELLED,
                                    turn_id,
                                    content,
                                    steps,
                                    "cancelled by Esc",
                                    130,
                                )
                            if result.code == "APPROVAL_DENIED":
                                return self._finish(
                                    AgentState.FAILED,
                                    turn_id,
                                    content,
                                    steps,
                                    "verification approval was denied",
                                    exit_code=3,
                                )
                            if not result.ok:
                                verification_failures += 1
                                if verification_failures >= 3:
                                    self._append_message(assistant)
                                    return self._finish(
                                        AgentState.FAILED,
                                        turn_id,
                                        content,
                                        steps,
                                        "verification failed after two repair attempts",
                                    )
                                verification_failed = True
                                self._emit(
                                    EventKind.WARNING,
                                    turn_id=turn_id,
                                    data={
                                        "code": "VERIFICATION_FAILED",
                                        "message": (
                                            "deterministic verification failed; "
                                            "the result was returned for repair"
                                        ),
                                        "attempt": verification_failures,
                                        "maximum_repairs": 2,
                                    },
                                )
                                break
                    if verification_failed:
                        continue
                    self._append_message(assistant)
                    return self._finish(
                        AgentState.COMPLETED, turn_id, content, steps, "assistant completed"
                    )

                self._append_message(assistant)

                context = self._tool_context(turn_id, cancel_event)
                for index, call in enumerate(tool_calls):
                    if cancel_event is not None and cancel_event.is_set():
                        self._append_unexecuted_tools(
                            tool_calls,
                            index,
                            code="CANCELLED",
                            summary="tool call cancelled before execution",
                        )
                        return self._finish(
                            AgentState.CANCELLED,
                            turn_id,
                            last_text,
                            steps,
                            "cancelled by Esc",
                            130,
                        )
                    if steps >= self.settings.agent.max_steps:
                        self._append_unexecuted_tools(
                            tool_calls,
                            index,
                            code="STEP_BUDGET_EXHAUSTED",
                            summary="tool call was not executed",
                        )
                        break
                    steps += 1
                    self._set_state(AgentState.TOOL_PENDING, turn_id, tool=call.name, step=steps)
                    self._emit(
                        EventKind.TOOL_CALL,
                        turn_id=turn_id,
                        data={"id": call.id, "name": call.name, "arguments": call.arguments},
                    )
                    self._set_state(AgentState.EXECUTING, turn_id, tool=call.name, step=steps)
                    context.operation_id = call.id
                    result = self.tools.execute(call.name, call.arguments, context)
                    change_id = result.data.get("change_id")
                    if isinstance(change_id, str):
                        change = next(
                            (item for item in self.working.changes if item.id == change_id),
                            None,
                        )
                        if change is not None:
                            self.sessions.append(
                                self.session_id,
                                CHANGE_RECORD_TYPE,
                                serialize_change(change),
                            )
                    self.working.recent_calls.append(
                        {
                            "name": call.name,
                            "arguments": call.arguments,
                            "result": result.model_dump(),
                        }
                    )
                    self.working.recent_calls = self.working.recent_calls[-12:]
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": result.model_dump_json(),
                    }
                    self._append_message(tool_message)
                    self._set_state(AgentState.OBSERVING, turn_id, tool=call.name, step=steps)
                    self._emit(
                        EventKind.TOOL_RESULT,
                        turn_id=turn_id,
                        data={"id": call.id, "name": call.name, "result": result.model_dump()},
                    )
                    if cancel_event is not None and cancel_event.is_set():
                        self._append_unexecuted_tools(
                            tool_calls,
                            index + 1,
                            code="CANCELLED",
                            summary="tool call cancelled before execution",
                        )
                        return self._finish(
                            AgentState.CANCELLED,
                            turn_id,
                            last_text,
                            steps,
                            "cancelled by Esc",
                            130,
                        )
                    signature = (
                        call.name
                        + ":"
                        + json.dumps(call.arguments, sort_keys=True, ensure_ascii=False)
                    )
                    if result.ok:
                        failed_signature = None
                        failed_count = 0
                    elif signature == failed_signature:
                        failed_count += 1
                    else:
                        failed_signature = signature
                        failed_count = 1
                    if failed_count == 2:
                        self._emit(
                            EventKind.WARNING,
                            turn_id=turn_id,
                            data={"message": "same tool call failed twice; loop guard armed"},
                        )
                    if failed_count >= 3:
                        return self._finish(
                            AgentState.FAILED,
                            turn_id,
                            last_text,
                            steps,
                            "loop guard stopped a third identical failure",
                        )
                    if result.code == "APPROVAL_DENIED" and not self.approval.interactive:
                        return self._finish(
                            AgentState.FAILED,
                            turn_id,
                            last_text,
                            steps,
                            "approval required in non-interactive mode",
                            exit_code=3,
                        )
            return self._finish(
                AgentState.FAILED, turn_id, last_text, steps, "tool step budget exhausted"
            )
        except KeyboardInterrupt:
            return self._finish(AgentState.CANCELLED, turn_id, last_text, steps, "cancelled", 130)
        except Exception as exc:
            self._emit(
                EventKind.ERROR,
                turn_id=turn_id,
                data={"message": f"{type(exc).__name__}: {exc}"},
            )
            return self._finish(
                AgentState.FAILED,
                turn_id,
                last_text,
                steps,
                f"internal error: {type(exc).__name__}: {exc}",
            )

    def _finish(
        self,
        status: AgentState,
        turn_id: str,
        content: str,
        steps: int,
        reason: str,
        exit_code: int | None = None,
    ) -> RunResult:
        code = exit_code if exit_code is not None else (0 if status is AgentState.COMPLETED else 1)
        if status is AgentState.COMPLETED and self.working.plan_turn_id == turn_id:
            completed = sum(item.get("status") == "completed" for item in self.working.plan)
            total = len(self.working.plan)
            if completed < total:
                self._emit(
                    EventKind.WARNING,
                    turn_id=turn_id,
                    data={
                        "code": "PLAN_INCOMPLETE",
                        "message": f"计划未闭环: 已完成 {completed}/{total} 步。",
                        "completed": completed,
                        "total": total,
                    },
                )
        self._set_state(status, turn_id, reason=reason, tool_steps=steps)
        self._emit(
            EventKind.DONE,
            turn_id=turn_id,
            state=status,
            data={"reason": reason, "exit_code": code, "tool_steps": steps},
        )
        self.sessions.append(
            self.session_id,
            "termination",
            {"status": status.value, "reason": reason, "exit_code": code},
        )
        if status is AgentState.COMPLETED:
            self.sessions.ensure_title(self.session_id, self.working.goal)
        return RunResult(status, code, self.session_id, content, steps, reason)
