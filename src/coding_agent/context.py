from __future__ import annotations

import json
from typing import Any

from coding_agent.tokens import count_tokens
from coding_agent.tools.base import WorkingState


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    text = json.dumps(messages, ensure_ascii=False, default=str)
    return count_tokens(text)


def estimate_request_tokens(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
) -> int:
    """Estimate the complete request, including function declarations."""

    total = estimate_tokens(messages)
    if tools:
        total += count_tokens(json.dumps(tools, ensure_ascii=False, default=str))
    return total


class ContextManager:
    def __init__(self, *, context_window: int, threshold: float = 0.7) -> None:
        self.context_window = context_window
        self.threshold = threshold

    def should_compact(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> bool:
        return estimate_request_tokens(messages, tools) >= int(self.context_window * self.threshold)

    def compact(
        self, messages: list[dict[str, Any]], working: WorkingState
    ) -> tuple[list[dict[str, Any]], str]:
        system_count = 0
        while system_count < len(messages) and messages[system_count].get("role") == "system":
            system_count += 1
        previous_summaries = [
            str(message.get("content", "")) for message in messages[:system_count]
        ]
        user_indices = [
            index
            for index in range(system_count, len(messages))
            if messages[index].get("role") == "user"
        ]
        if len(user_indices) < 2:
            return messages, ""
        # A turn begins at a user message and includes every assistant/tool exchange
        # up to the next user message. Keep four complete turns rather than eight
        # arbitrary messages, which can split a Gemini function-call group.
        retained_turns = min(4, len(user_indices) - 1)
        recent_start = user_indices[-retained_turns]
        recent = messages[recent_start:]
        older = messages[system_count:recent_start]
        if not older:
            return messages, ""
        previous_goal = next(
            (
                line.removeprefix("Goal: ")
                for summary in previous_summaries
                for line in summary.splitlines()
                if line.startswith("Goal: ")
            ),
            "",
        )
        first_goal = previous_goal or next(
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
        prior_turn_notes: list[str] = []
        for message in older:
            role = message.get("role")
            content = str(message.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                normalized = " ".join(content.split())
                prior_turn_notes.append(f"{role}: {normalized[:500]}")
            if role != "tool":
                continue
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
                "Prior turn notes: " + (" | ".join(prior_turn_notes[-8:]) or "none recorded"),
            ]
        )
        compacted = [{"role": "system", "content": summary}, *recent]
        return compacted, summary
