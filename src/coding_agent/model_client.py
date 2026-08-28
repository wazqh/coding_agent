from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any, cast

from openai import OpenAI

from coding_agent.events import ModelStreamEvent, ToolCall, Usage


class ModelProtocolError(RuntimeError):
    pass


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


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
        self._client = client or OpenAI(api_key=api_key, base_url=base_url)

    def _gemini_extra_body(self) -> dict[str, Any] | None:
        if not self.base_url:
            return None
        if "generativelanguage.googleapis.com" not in self.base_url:
            return None
        if not self.model.startswith("gemini-"):
            return None
        return {
            "google": {
                "thinking_config": {
                    "thinking_level": "low",
                    "include_thoughts": True,
                }
            }
        }

    def _create_stream(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> Any:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
        }
        if tools:
            request["tools"] = list(tools)
            request["tool_choice"] = "auto"
        request["stream_options"] = {"include_usage": True}
        extra_body = self._gemini_extra_body()
        if extra_body is not None:
            request["extra_body"] = {"extra_body": extra_body}
        return self._client.chat.completions.stream(**request)

    @staticmethod
    def _thought_signature(obj: Any) -> str | None:
        for key in ("thought_signature", "thoughtSignature"):
            value = _value(obj, key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status in {408, 409, 429} or (isinstance(status, int) and status >= 500):
            return True
        name = type(exc).__name__.lower()
        return any(part in name for part in ("connection", "timeout", "ratelimit"))

    def stream(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> Iterator[ModelStreamEvent]:
        """Yield text deltas, assembled calls, usage, and a terminal event."""

        for attempt in range(self.max_retries + 1):
            emitted = False
            try:
                stream_manager = self._create_stream(messages, tools)
                finish_reason: str | None = None
                with stream_manager as stream:
                    for event in stream:
                        kind = _value(event, "type")
                        if kind == "content.delta":
                            content = _value(event, "delta")
                            if content:
                                emitted = True
                                yield ModelStreamEvent(type="text_delta", text=str(content))
                    completion = stream.get_final_completion()
                choices = _value(completion, "choices", []) or []
                message = _value(choices[0], "message", {}) if choices else {}
                if not emitted:
                    content = _value(message, "content")
                    if content:
                        content_text = str(content)
                        yield ModelStreamEvent(type="text_delta", text=content_text)
                finish_reason = _value(choices[0], "finish_reason") if choices else None
                assembled: list[ToolCall] = []
                for index, raw_call in enumerate(_value(message, "tool_calls", []) or []):
                    function = _value(raw_call, "function", {}) or {}
                    arguments_text = str(_value(function, "arguments", "") or "")
                    try:
                        arguments = json.loads(arguments_text or "{}")
                    except json.JSONDecodeError as exc:
                        name = str(_value(function, "name", "") or "tool")
                        raise ModelProtocolError(
                            f"invalid JSON arguments for {name}: {exc.msg}"
                        ) from exc
                    if not isinstance(arguments, dict):
                        raise ModelProtocolError("tool arguments must decode to an object")
                    assembled.append(
                        ToolCall(
                            id=str(_value(raw_call, "id", "") or f"call_{index}"),
                            name=str(_value(function, "name", "") or ""),
                            arguments=arguments,
                            thought_signature=self._thought_signature(function)
                            or self._thought_signature(raw_call),
                        )
                    )
                if assembled:
                    yield ModelStreamEvent(type="tool_calls", tool_calls=assembled)
                raw_usage = _value(completion, "usage")
                if raw_usage is not None:
                    yield ModelStreamEvent(
                        type="usage",
                        usage=Usage(
                            prompt_tokens=int(_value(raw_usage, "prompt_tokens", 0) or 0),
                            completion_tokens=int(_value(raw_usage, "completion_tokens", 0) or 0),
                            total_tokens=int(_value(raw_usage, "total_tokens", 0) or 0),
                        ),
                    )
                yield ModelStreamEvent(type="done", finish_reason=finish_reason)
                return
            except Exception as exc:
                if not emitted and attempt < self.max_retries and self._retryable(exc):
                    delay = min(8.0, 0.5 * (2**attempt)) + random.random() * 0.1  # nosec B311
                    self._sleep(delay)
                    continue
                yield ModelStreamEvent(type="error", error=str(exc))
                return
