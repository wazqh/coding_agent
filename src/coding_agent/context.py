from __future__ import annotations

import json
import importlib
from typing import Any

from coding_agent.tools.base import WorkingState


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    text = json.dumps(messages, ensure_ascii=False, default=str)
    try:
        tiktoken = importlib.import_module("tiktoken")
        encoded: list[int] = tiktoken.get_encoding("cl100k_base").encode(text)
        return len(encoded)
    except (ImportError, KeyError, AttributeError):
        return max(1, len(text) // 4)


class ContextManager:
    def __init__(self, *, context_window: int, threshold: float = 0.7) -> None:
        self.context_window = context_window
        self.threshold = threshold

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        return estimate_tokens(messages) >= int(self.context_window * self.threshold)

    def compact(
        self, messages: list[dict[str, Any]], working: WorkingState
    ) -> tuple[list[dict[str, Any]], str]:
        if len(messages) <= 9:
            return messages, ""
        system = [message for message in messages[:1] if message.get("role") == "system"]
        recent = messages[-8:]
        older = messages[len(system) : -8]
        first_goal = next(
            (str(message.get("content", "")) for message in messages if message.get("role") == "user"),
            working.goal,
        )
        completed = [
            item["step"] for item in working.plan if item.get("status") == "completed"
        ]
        pending = [item["step"] for item in working.plan if item.get("status") != "completed"]
        failures: list[str] = []
        evidence: list[str] = []
        for message in older:
            if message.get("role") != "tool":
                continue
            content = str(message.get("content", ""))
            if '"ok":false' in content.replace(" ", "").casefold():
                failures.append(content[:300])
            if "passed" in content.casefold() or "exit_code" in content:
                evidence.append(content[:300])
        summary = "\n".join(
            [
                "Conversation summary (original transcript remains in the session log):",
                f"Goal: {first_goal[:1000]}",
                "Constraints: obey workspace isolation, project instructions, approvals, and user intent.",
                "Completed changes: " + ("; ".join(completed) or "none recorded"),
                "Failed approaches: " + ("; ".join(failures[-4:]) or "none recorded"),
                "Test evidence: " + ("; ".join(evidence[-4:]) or "none recorded"),
                "Pending work: " + ("; ".join(pending) or "none recorded"),
            ]
        )
        compacted = [*system, {"role": "system", "content": summary}, *recent]
        return compacted, summary
