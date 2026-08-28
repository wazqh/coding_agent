from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from coding_agent.config import Settings
from coding_agent.context import ContextManager, estimate_tokens
from coding_agent.events import AgentEvent, AgentState, EventKind, ToolCall
from coding_agent.memory import MemoryStore
from coding_agent.model_client import ModelClient
from coding_agent.project import project_id
from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.safety.paths import WorkspacePaths
from coding_agent.session import SessionError, SessionStore
from coding_agent.skills import SkillError, SkillRegistry
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
    ) -> None:
        self.settings = settings
        self.model = model
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
        if session_id is not None:
            self._restore(session_id)

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
        self.conversation = [record["data"] for record in records if record["type"] == "message"]
        for record in records:
            if record["type"] != "event":
                continue
            data = record["data"]
            if data.get("kind") == EventKind.PLAN.value:
                self.working.plan = data.get("data", {}).get("plan", [])
            elif data.get("kind") == EventKind.SKILL.value and self.skills is not None:
                name = data.get("data", {}).get("name")
                if not isinstance(name, str):
                    continue
                try:
                    self.skills.activate(name)
                except SkillError:
                    continue
                if name not in self.working.active_skills:
                    self.working.active_skills.append(name)

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
                "You are Forge, a local CLI coding agent. Complete the user's task using the "
                "provided local tools."
            ),
            (
                "Never claim a tool ran when it did not. Read files before editing; use returned "
                "SHA-256 values for edits and overwrites. Treat tool failures as observations and "
                "correct the plan or arguments. Do not reveal hidden chain-of-thought; communicate "
                "only concise plans, actions, results, and relevant rationale."
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

    def _tool_context(self, turn_id: str) -> ToolContext:
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
        )

    def manual_compact(self) -> str:
        compacted, summary = self.context.compact(self.conversation, self.working)
        if summary:
            self.conversation = compacted
            self.sessions.append(
                self.session_id,
                "compact",
                {"summary": summary, "manual": True},
            )
        return summary

    def run_turn(self, user_input: str) -> RunResult:
        turn_id = uuid4().hex[:16]
        started = self.monotonic()
        self.working.goal = user_input
        self._append_message({"role": "user", "content": user_input})
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
        steps = 0
        last_text = ""
        failed_signature: str | None = None
        failed_count = 0

        try:
            while steps < self.settings.agent.max_steps:
                if self.monotonic() - started >= self.settings.agent.max_seconds:
                    return self._finish(
                        AgentState.FAILED,
                        turn_id,
                        last_text,
                        steps,
                        "turn time budget exhausted",
                    )
                request_messages = [
                    {"role": "system", "content": system_prompt},
                    *self.conversation,
                ]
                if self.context.should_compact(request_messages):
                    before = estimate_tokens(request_messages)
                    compacted, summary = self.context.compact(self.conversation, self.working)
                    if summary:
                        self.conversation = compacted
                        self.sessions.append(
                            self.session_id,
                            "compact",
                            {"summary": summary, "manual": False, "tokens_before": before},
                        )
                        self._emit(
                            EventKind.COMPACT,
                            turn_id=turn_id,
                            data={"tokens_before": before, "summary": summary},
                        )
                        request_messages = [
                            {"role": "system", "content": system_prompt},
                            *self.conversation,
                        ]
                self._set_state(AgentState.THINKING, turn_id, step=steps)
                content_parts: list[str] = []
                tool_calls: list[ToolCall] = []
                model_error: str | None = None
                for event in self.model.stream(request_messages, self.tools.schemas()):
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
                    assistant["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            },
                        }
                        for call in tool_calls
                    ]
                self._append_message(assistant)
                if not tool_calls:
                    if content.strip():
                        return self._finish(
                            AgentState.COMPLETED, turn_id, content, steps, "assistant completed"
                        )
                    return self._finish(
                        AgentState.FAILED,
                        turn_id,
                        content,
                        steps,
                        "model returned neither text nor tool calls",
                    )

                context = self._tool_context(turn_id)
                for index, call in enumerate(tool_calls):
                    if steps >= self.settings.agent.max_steps:
                        for skipped in tool_calls[index:]:
                            self._append_message(
                                {
                                    "role": "tool",
                                    "tool_call_id": skipped.id,
                                    "name": skipped.name,
                                    "content": json.dumps(
                                        {
                                            "ok": False,
                                            "code": "STEP_BUDGET_EXHAUSTED",
                                            "summary": "tool call was not executed",
                                            "data": {},
                                            "retryable": False,
                                            "truncated": False,
                                        }
                                    ),
                                }
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
                    result = self.tools.execute(call.name, call.arguments, context)
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
        return RunResult(status, code, self.session_id, content, steps, reason)
