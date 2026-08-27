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
        self.max_retries = max_retries
        self._sleep = sleep
        self._client = client or OpenAI(api_key=api_key, base_url=base_url)

    def _create_stream(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> Iterable[Any]:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            request["tools"] = list(tools)
            request["tool_choice"] = "auto"
        return cast(Iterable[Any], self._client.chat.completions.create(**request))

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
                chunks = self._create_stream(messages, tools)
                calls: dict[int, dict[str, str]] = {}
                finish_reason: str | None = None
                usage: Usage | None = None
                for chunk in chunks:
                    raw_usage = _value(chunk, "usage")
                    if raw_usage is not None:
                        usage = Usage(
                            prompt_tokens=int(_value(raw_usage, "prompt_tokens", 0) or 0),
                            completion_tokens=int(_value(raw_usage, "completion_tokens", 0) or 0),
                            total_tokens=int(_value(raw_usage, "total_tokens", 0) or 0),
                        )
                    choices = _value(chunk, "choices", []) or []
                    if not choices:
                        continue
                    choice = choices[0]
                    finish_reason = _value(choice, "finish_reason") or finish_reason
                    delta = _value(choice, "delta", {}) or {}
                    content = _value(delta, "content")
                    if content:
                        emitted = True
                        yield ModelStreamEvent(type="text_delta", text=str(content))
                    for fragment in _value(delta, "tool_calls", []) or []:
                        index = int(_value(fragment, "index", 0) or 0)
                        target = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        fragment_id = _value(fragment, "id")
                        if fragment_id:
                            target["id"] += str(fragment_id)
                        function = _value(fragment, "function", {}) or {}
                        name = _value(function, "name")
                        arguments = _value(function, "arguments")
                        if name:
                            target["name"] += str(name)
                        if arguments:
                            target["arguments"] += str(arguments)
                assembled: list[ToolCall] = []
                for index in sorted(calls):
                    item = calls[index]
                    try:
                        arguments = json.loads(item["arguments"] or "{}")
                    except json.JSONDecodeError as exc:
                        raise ModelProtocolError(
                            f"invalid JSON arguments for {item['name'] or 'tool'}: {exc.msg}"
                        ) from exc
                    if not isinstance(arguments, dict):
                        raise ModelProtocolError("tool arguments must decode to an object")
                    assembled.append(
                        ToolCall(
                            id=item["id"] or f"call_{index}",
                            name=item["name"],
                            arguments=arguments,
                        )
                    )
                if assembled:
                    yield ModelStreamEvent(type="tool_calls", tool_calls=assembled)
                if usage is not None:
                    yield ModelStreamEvent(type="usage", usage=usage)
                yield ModelStreamEvent(type="done", finish_reason=finish_reason)
                return
            except Exception as exc:
                if not emitted and attempt < self.max_retries and self._retryable(exc):
                    delay = min(8.0, 0.5 * (2**attempt)) + random.random() * 0.1
                    self._sleep(delay)
                    continue
                yield ModelStreamEvent(type="error", error=str(exc))
                return
