from __future__ import annotations

import json
from typing import Any

from coding_agent.tokens import count_tokens
from coding_agent.tools.base import WorkingState


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    text = json.dumps(messages, ensure_ascii=False, default=str)
    return count_tokens(text)


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
        system_count = len(system)
        latest_user = next(
            (
                index
                for index in range(len(messages) - 1, system_count - 1, -1)
                if messages[index].get("role") == "user"
            ),
            len(messages),
        )
        # Keep at least four recent message pairs, and never split the active
        # user turn. Gemini validates every tool-call signature in that turn.
        recent_start = min(max(system_count, len(messages) - 8), latest_user)
        recent = messages[recent_start:]
        older = messages[system_count:recent_start]
        if not older:
            return messages, ""
        first_goal = next(
            (
                str(message.get("content", ""))
                for message in messages
                if message.get("role") == "user"
            ),
            working.goal,
        )
        completed = [item["step"] for item in working.plan if item.get("status") == "completed"]
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
                "Constraints: obey workspace isolation, project instructions, approvals, "
                "and user intent.",
                "Completed changes: " + ("; ".join(completed) or "none recorded"),
                "Failed approaches: " + ("; ".join(failures[-4:]) or "none recorded"),
                "Test evidence: " + ("; ".join(evidence[-4:]) or "none recorded"),
                "Pending work: " + ("; ".join(pending) or "none recorded"),
            ]
        )
        compacted = [*system, {"role": "system", "content": summary}, *recent]
        return compacted, summary
