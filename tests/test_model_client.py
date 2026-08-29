from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from coding_agent.model_client import ModelClient


class FakeStream:
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self.chunks = chunks
        self.closed = False

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.chunks)

    def close(self) -> None:
        self.closed = True


class FakeCompletions:
    def __init__(self, streams: list[Any]) -> None:
        self.streams = streams
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeStream:
        self.requests.append(kwargs)
        value = self.streams.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeClient:
    def __init__(self, streams: list[Any]) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(streams)


def test_stream_assembles_indexless_gemini_tool_call_and_signature() -> None:
    stream = FakeStream(
        [
            {"choices": [{"index": None, "delta": {"content": "Checking. "}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": None,
                                    "id": "call_1",
                                    "type": "function",
                                    "extra_content": {"google": {"thought_signature": "sig-1"}},
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": None,
                                    "function": {"arguments": '"README.md"}'},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {
                "choices": [],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
        ]
    )
    fake = FakeClient([stream])
    client = ModelClient(
        model="gemini-3.7-flash",
        api_key="x",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        client=fake,
        max_retries=0,
    )

    events = list(client.stream([{"role": "user", "content": "x"}], []))

    assert events[0].text == "Checking. "
    calls = next(event.tool_calls for event in events if event.type == "tool_calls")
    assert calls[0].name == "read_file"
    assert calls[0].arguments == {"path": "README.md"}
    assert calls[0].thought_signature == "sig-1"
    assert next(event.usage for event in events if event.type == "usage").total_tokens == 5
    request = fake.chat.completions.requests[0]
    assert request["stream"] is True
    assert request["stream_options"] == {"include_usage": True}
    assert "extra_body" not in request
    assert stream.closed


def test_stream_keeps_parallel_indexless_calls_separate_by_id() -> None:
    stream = FakeStream(
        [
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": None,
                                    "id": "paris",
                                    "extra_content": {
                                        "google": {"thought_signature": "sig-parallel"}
                                    },
                                    "function": {
                                        "name": "weather",
                                        "arguments": '{"city":"Paris"}',
                                    },
                                },
                                {
                                    "index": None,
                                    "id": "london",
                                    "function": {
                                        "name": "weather",
                                        "arguments": '{"city":"London"}',
                                    },
                                },
                            ]
                        },
                    }
                ]
            }
        ]
    )
    client = ModelClient(model="gemini", api_key="x", client=FakeClient([stream]))

    events = list(client.stream([], []))

    calls = next(event.tool_calls for event in events if event.type == "tool_calls")
    assert [call.id for call in calls] == ["paris", "london"]
    assert [call.arguments["city"] for call in calls] == ["Paris", "London"]
    assert calls[0].thought_signature == "sig-parallel"
    assert calls[1].thought_signature is None


def test_retry_before_output_and_invalid_json() -> None:
    error = RuntimeError("rate limited")
    error.status_code = 429  # type: ignore[attr-defined]
    sleeps: list[float] = []
    stream = FakeStream(
        [
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "x",
                                    "type": "function",
                                    "function": {"name": "read_file", "arguments": "{"},
                                }
                            ]
                        },
                    }
                ]
            }
        ]
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
    assert stream.closed


def test_non_retryable_authentication_error_is_not_retried() -> None:
    error = RuntimeError("invalid API key")
    error.status_code = 401  # type: ignore[attr-defined]
    fake = FakeClient([error])
    client = ModelClient(model="m", api_key="x", client=fake, max_retries=3)

    final = list(client.stream([], []))[-1]

    assert final.type == "error"
    assert len(fake.chat.completions.requests) == 1


@pytest.mark.parametrize(
    ("compatibility", "keeps_signature"), [("openai", False), ("gemini", True)]
)
def test_request_filters_google_thought_signature_by_provider(
    compatibility: str, keeps_signature: bool
) -> None:
    fake = FakeClient([FakeStream([])])
    client = ModelClient(
        model="m",
        api_key="x",
        client=fake,
        compatibility=compatibility,
        max_retries=0,
    )
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                    "extra_content": {"google": {"thought_signature": "sig-1"}},
                }
            ],
        }
    ]

    list(client.stream(messages, []))

    request_call = fake.chat.completions.requests[0]["messages"][0]["tool_calls"][0]
    assert ("extra_content" in request_call) is keeps_signature
    assert "extra_content" in messages[0]["tool_calls"][0]  # type: ignore[index]


def test_stream_is_closed_when_iteration_is_cancelled() -> None:
    class InterruptingStream(FakeStream):
        def __iter__(self) -> Iterator[dict[str, Any]]:
            raise KeyboardInterrupt
            yield {}

    stream = InterruptingStream([])
    client = ModelClient(
        model="m",
        api_key="x",
        client=FakeClient([stream]),
        max_retries=0,
    )

    with pytest.raises(KeyboardInterrupt):
        list(client.stream([], []))
    assert stream.closed
