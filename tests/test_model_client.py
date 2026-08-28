from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from coding_agent.model_client import ModelClient


class FakeStream:
    def __init__(self, events: list[dict[str, Any]], completion: dict[str, Any]) -> None:
        self.events = events
        self.completion = completion
        self.closed = False

    def __enter__(self) -> FakeStream:
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self.closed = True

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.events)

    def get_final_completion(self) -> dict[str, Any]:
        return self.completion


class FakeCompletions:
    def __init__(self, streams: list[Any]) -> None:
        self.streams = streams
        self.requests: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> FakeStream:
        self.requests.append(kwargs)
        value = self.streams.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeClient:
    def __init__(self, streams: list[Any]) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(streams)


def test_stream_assembles_tool_call_and_thought_signature() -> None:
    stream = FakeStream(
        events=[{"type": "content.delta", "delta": "Checking. "}],
        completion={
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": '{"path":"a.py"}',
                                    "thought_signature": "sig-1",
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        },
    )
    client = ModelClient(
        model="gemini-3.7-flash",
        api_key="x",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        client=FakeClient([stream]),
        max_retries=0,
    )
    events = list(client.stream([{"role": "user", "content": "x"}], []))
    assert events[0].text == "Checking. "
    calls = next(event.tool_calls for event in events if event.type == "tool_calls")
    assert calls[0].name == "read_file"
    assert calls[0].arguments == {"path": "a.py"}
    assert calls[0].thought_signature == "sig-1"
    assert next(event.usage for event in events if event.type == "usage").total_tokens == 5
    request = client._client.chat.completions.requests[0]
    assert request["extra_body"]["google"]["thinking_config"]["include_thoughts"] is True
    assert stream.closed


def test_retry_before_output_and_invalid_json() -> None:
    error = RuntimeError("rate limited")
    error.status_code = 429  # type: ignore[attr-defined]
    sleeps: list[float] = []
    stream = FakeStream(
        events=[],
        completion={
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "tool_calls": [
                            {
                                "id": "x",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": "{"},
                            }
                        ]
                    },
                }
            ]
        },
    )
    client = ModelClient(
        model="m",
        api_key="x",
        client=FakeClient([error, stream]),
        max_retries=1,
        sleep=sleeps.append,
    )
    final = list(client.stream([], []))[-1]
    assert final.type == "error"
    assert "invalid JSON" in (final.error or "")
    assert sleeps


def test_stream_is_closed_when_iteration_is_cancelled() -> None:
    class InterruptingStream(FakeStream):
        def __iter__(self) -> Iterator[dict[str, Any]]:
            raise KeyboardInterrupt
            yield {}

    stream = InterruptingStream([], {"choices": []})
    client = ModelClient(
        model="m",
        api_key="x",
        client=FakeClient([stream]),
        max_retries=0,
    )
    with pytest.raises(KeyboardInterrupt):
        list(client.stream([], []))
    assert stream.closed
