from __future__ import annotations

from typing import Any

from coding_agent.model_client import ModelClient


class FakeCompletions:
    def __init__(self, streams: list[Any]) -> None:
        self.streams = streams
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any):
        self.requests.append(kwargs)
        value = self.streams.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeClient:
    def __init__(self, streams: list[Any]) -> None:
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(streams)


def test_stream_assembles_fragmented_tool_call() -> None:
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "content": "Checking. ",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "read_", "arguments": '{"pa'},
                            }
                        ],
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
                                "index": 0,
                                "function": {"name": "file", "arguments": 'th":"a.py"}'},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        },
    ]
    client = ModelClient(model="m", api_key="x", client=FakeClient([chunks]), max_retries=0)
    events = list(client.stream([{"role": "user", "content": "x"}], []))
    assert events[0].text == "Checking. "
    calls = next(event.tool_calls for event in events if event.type == "tool_calls")
    assert calls[0].name == "read_file"
    assert calls[0].arguments == {"path": "a.py"}
    assert next(event.usage for event in events if event.type == "usage").total_tokens == 5


def test_retry_before_output_and_invalid_json() -> None:
    error = RuntimeError("rate limited")
    error.status_code = 429  # type: ignore[attr-defined]
    sleeps: list[float] = []
    chunks = [{"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}]
    client = ModelClient(
        model="m",
        api_key="x",
        client=FakeClient([error, chunks]),
        max_retries=1,
        sleep=sleeps.append,
    )
    assert any(event.text == "ok" for event in client.stream([], []))
    assert sleeps

    bad = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "x",
                                "function": {"name": "read_file", "arguments": "{"},
                            }
                        ]
                    }
                }
            ]
        }
    ]
    malformed = ModelClient(model="m", api_key="x", client=FakeClient([bad]), max_retries=0)
    final = list(malformed.stream([], []))[-1]
    assert final.type == "error"
    assert "invalid JSON" in (final.error or "")
