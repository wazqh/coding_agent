from __future__ import annotations

import itertools
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from coding_agent.config import Settings
from coding_agent.events import ModelStreamEvent

_TEMP_COUNTER = itertools.count()


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Use a pre-created sandbox temp root when the execution environment requires it."""

    override = os.environ.get("CODING_AGENT_TEST_TMP")
    if not override:
        return tmp_path_factory.mktemp(request.node.name[:30])
    name = "".join(character if character.isalnum() else "_" for character in request.node.name)
    path = Path(override) / f"{next(_TEMP_COUNTER):03d}_{name[:60]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        cwd=tmp_path,
        data_dir=tmp_path / "data",
        model={"name": "fake-model", "api_key": "test-key", "max_retries": 0},
        agent={
            "max_steps": 40,
            "max_seconds": 60,
            "context_window": 4096,
            "command_timeout": 10,
        },
    )


class FakeModel:
    def __init__(self, responses: list[list[ModelStreamEvent]]) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
        self.model = "fake-model"

    def stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> Iterator[ModelStreamEvent]:
        self.requests.append((messages, tools))
        yield from self.responses.pop(0)
