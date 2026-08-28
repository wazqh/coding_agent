from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import suppress
from typing import Any

from openai import OpenAI

from coding_agent.events import ModelStreamEvent, ToolCall, Usage


class ModelProtocolError(RuntimeError):
    pass


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _nested_value(obj: Any, *keys: str) -> Any:
    value = obj
    for key in keys:
        value = _value(value, key)
        if value is None:
            return None
    return value


class ModelClient:
    """Small OpenAI-compatible adapter; all agent behavior stays local."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str | None = None,
        max_retries: int = 3,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")
        self.model = model
        self.base_url = base_url
        self.max_retries = max_retries
        self._sleep = sleep
        # Retry in one place so the controller's configured retry budget is exact.
        self._client = client or OpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    def _create_stream(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> Any:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            request["tools"] = list(tools)
            request["tool_choice"] = "auto"
        return self._client.chat.completions.create(**request)

    @staticmethod
    def _thought_signature(raw_call: Any) -> str | None:
        """Read both the documented Gemini location and legacy proxy variants."""

        candidates = (
            _nested_value(raw_call, "extra_content", "google", "thought_signature"),
            _nested_value(raw_call, "extra_content", "google", "thoughtSignature"),
            _value(raw_call, "thought_signature"),
            _value(raw_call, "thoughtSignature"),
            _value(_value(raw_call, "function", {}), "thought_signature"),
        )
        return next((str(value) for value in candidates if value), None)

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status in {408, 429} or (isinstance(status, int) and status >= 500):
            return True
        name = type(exc).__name__.lower()
        return any(part in name for part in ("connection", "timeout", "ratelimit"))

    @staticmethod
    def _tool_buffer(buffers: list[dict[str, Any]], raw_call: Any) -> dict[str, Any]:
        """Resolve a tool delta without assuming providers always send an index."""

        raw_index = _value(raw_call, "index")
        if isinstance(raw_index, int) and raw_index >= 0:
            while len(buffers) <= raw_index:
                buffers.append({"id": "", "name": "", "arguments": "", "signature": None})
            return buffers[raw_index]

        call_id = str(_value(raw_call, "id", "") or "")
        if call_id:
            for buffer in buffers:
                if buffer["id"] == call_id:
                    return buffer
            buffer = {"id": call_id, "name": "", "arguments": "", "signature": None}
            buffers.append(buffer)
            return buffer

        if not buffers:
            buffers.append({"id": "", "name": "", "arguments": "", "signature": None})
        if len(buffers) > 1:
            function_name = str(_value(_value(raw_call, "function", {}) or {}, "name", "") or "")
            matches = [buffer for buffer in buffers if buffer["name"] == function_name]
            if function_name and len(matches) == 1:
                return matches[0]
            raise ModelProtocolError("parallel tool-call delta is missing both index and call id")
        return buffers[-1]

    @staticmethod
    def _append_tool_delta(buffer: dict[str, Any], raw_call: Any) -> None:
        call_id = _value(raw_call, "id")
        if call_id:
            buffer["id"] = str(call_id)
        function = _value(raw_call, "function", {}) or {}
        name = _value(function, "name")
        if name:
            buffer["name"] += str(name)
        arguments = _value(function, "arguments")
        if isinstance(arguments, str):
            buffer["arguments"] += arguments
        elif arguments is not None:
            buffer["arguments"] += json.dumps(arguments, ensure_ascii=False)
        signature = ModelClient._thought_signature(raw_call)
        if signature:
            buffer["signature"] = signature

    @staticmethod
    def _assemble_tool_calls(buffers: list[dict[str, Any]]) -> list[ToolCall]:
        assembled: list[ToolCall] = []
        for index, buffer in enumerate(buffers):
            arguments_text = str(buffer["arguments"] or "")
            try:
                arguments = json.loads(arguments_text or "{}")
            except json.JSONDecodeError as exc:
                name = str(buffer["name"] or "tool")
                raise ModelProtocolError(f"invalid JSON arguments for {name}: {exc.msg}") from exc
            if not isinstance(arguments, dict):
                raise ModelProtocolError("tool arguments must decode to an object")
            name = str(buffer["name"] or "")
            if not name:
                raise ModelProtocolError("tool call is missing a function name")
            assembled.append(
                ToolCall(
                    id=str(buffer["id"] or f"call_{index}"),
                    name=name,
                    arguments=arguments,
                    thought_signature=buffer["signature"],
                )
            )
        return assembled

    def stream(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> Iterator[ModelStreamEvent]:
        """Yield text deltas, manually assembled calls, usage, and a terminal event."""

        for attempt in range(self.max_retries + 1):
            emitted = False
            raw_stream: Any | None = None
            try:
                # The SDK's high-level `.stream()` accumulator indexes tool deltas.
                # Some compatible providers omit that index, so consume raw chunks.
                raw_stream = self._create_stream(messages, tools)
                finish_reason: str | None = None
                tool_buffers: list[dict[str, Any]] = []
                usage: Usage | None = None
                for chunk in raw_stream:
                    raw_usage = _value(chunk, "usage")
                    if raw_usage is not None:
                        usage = Usage(
                            prompt_tokens=int(_value(raw_usage, "prompt_tokens", 0) or 0),
                            completion_tokens=int(_value(raw_usage, "completion_tokens", 0) or 0),
                            total_tokens=int(_value(raw_usage, "total_tokens", 0) or 0),
                        )
                    choices = _value(chunk, "choices", []) or []
                    for choice in choices:
                        reason = _value(choice, "finish_reason")
                        if reason:
                            finish_reason = str(reason)
                        delta = _value(choice, "delta", {}) or {}
                        content = _value(delta, "content")
                        if content:
                            emitted = True
                            yield ModelStreamEvent(type="text_delta", text=str(content))
                        for raw_call in _value(delta, "tool_calls", []) or []:
                            buffer = self._tool_buffer(tool_buffers, raw_call)
                            self._append_tool_delta(buffer, raw_call)

                assembled = self._assemble_tool_calls(tool_buffers)
                if assembled:
                    yield ModelStreamEvent(type="tool_calls", tool_calls=assembled)
                if usage is not None:
                    yield ModelStreamEvent(type="usage", usage=usage)
                yield ModelStreamEvent(type="done", finish_reason=finish_reason)
                return
            except Exception as exc:
                if not emitted and attempt < self.max_retries and self._retryable(exc):
                    delay = min(8.0, 0.5 * (2**attempt)) + random.random() * 0.1  # nosec B311
                    self._sleep(delay)
                    continue
                yield ModelStreamEvent(type="error", error=str(exc))
                return
            finally:
                close = getattr(raw_stream, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()
