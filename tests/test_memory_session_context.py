from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.memory import MemoryError, MemoryKind, MemoryStore


def test_memory_approval_dedup_query_forget_and_secret(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    data = tmp_path / "data"
    store = MemoryStore(data_dir=data, workspace=workspace, enabled=True)
    candidate = store.propose(
        kind=MemoryKind.COMMAND,
        content="Run pytest -q before committing",
        evidence_session_id="session",
    )
    assert store.list() == [], "proposals must not persist before approval"
    first = store.approve(candidate)
    duplicate = store.approve(candidate)
    assert first.id == duplicate.id
    selected = store.query("please run pytest", max_tokens=100)
    assert [item.id for item in selected] == [first.id]
    assert store.forget(first.id)
    assert store.list() == []
    with pytest.raises(MemoryError):
        store.remember(content="api_key=sk-abcdefghijklmnop", session_id="session")
    with pytest.raises(MemoryError):
        store.remember(content="```python\n" + "x = 1\n" * 100 + "```", session_id="session")


def test_memory_isolation_and_disabled(tmp_path: Path) -> None:
    data = tmp_path / "data"
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    # Keep the isolation assertion valid even when the sandbox temp root itself
    # lives inside this repository.
    (one / ".git").mkdir()
    (two / ".git").mkdir()
    first = MemoryStore(data_dir=data, workspace=one, enabled=True)
    second = MemoryStore(data_dir=data, workspace=two, enabled=True)
    first.remember(content="This project uses pytest", session_id="one")
    assert second.list() == []
    first.enabled = False
    assert first.query("pytest") == []
    first.clear()
    assert first.list() == []
