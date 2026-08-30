from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psutil
import pytest
from conftest import FakeModel

import coding_agent.safety.commands as command_module
import coding_agent.safety.paths as path_module
from coding_agent.config import Settings
from coding_agent.controller import AgentController
from coding_agent.events import AgentState, EventKind, ModelStreamEvent, Usage
from coding_agent.memory import MemoryError, MemoryKind, MemoryStore
from coding_agent.safety.approval import ApprovalDecision, ApprovalPolicy, ApprovalRequest
from coding_agent.safety.commands import CommandPolicy
from coding_agent.safety.paths import PathSafetyError, WorkspacePaths, atomic_write_text
from coding_agent.session import SessionStore
from coding_agent.skills import SkillRegistry
from coding_agent.tools.registry import default_registry


def make_controller(
    settings: Settings,
    model: object,
    *,
    sessions: SessionStore | None = None,
    skills: SkillRegistry | None = None,
    session_id: str | None = None,
    events: list[Any] | None = None,
) -> AgentController:
    return AgentController(
        settings=settings,
        model=model,  # type: ignore[arg-type]
        tools=default_registry(),
        sessions=sessions or SessionStore(settings.data_dir),
        approval=ApprovalPolicy("auto"),
        skills=skills,
        session_id=session_id,
        event_sink=events.append if events is not None else None,
    )


def test_controller_automatic_compaction_and_usage(settings: Settings) -> None:
    settings.agent.context_window = 1
    model = FakeModel(
        [
            [
                ModelStreamEvent(
                    type="usage",
                    usage=Usage(prompt_tokens=10, completion_tokens=2, total_tokens=12),
                ),
                ModelStreamEvent(type="text_delta", text="done"),
                ModelStreamEvent(type="done", finish_reason="stop"),
            ]
        ]
    )
    events: list[Any] = []
    controller = make_controller(settings, model, events=events)
    controller.conversation = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"message {index}"}
        for index in range(12)
    ]
    result = controller.run_turn("finish")
    assert result.status is AgentState.COMPLETED
    assert any(event.kind is EventKind.COMPACT for event in events)
    assert any(event.kind is EventKind.USAGE for event in events)
    assert any(
        record["type"] == "compact" for record in controller.sessions.replay(result.session_id)
    )


def test_controller_compacts_only_completed_turns_before_appending_new_user(
    settings: Settings,
) -> None:
    settings.agent.context_window = 1
    model = FakeModel(
        [[ModelStreamEvent(type="text_delta", text="done"), ModelStreamEvent(type="done")]]
    )
    controller = make_controller(settings, model)
    controller.conversation = [
        {"role": "user", "content": f"request {index}"}
        if index % 2 == 0
        else {"role": "assistant", "content": f"answer {index}"}
        for index in range(12)
    ]
    observed: list[list[dict[str, Any]]] = []
    original_compact = controller.context.compact

    def capture(
        messages: list[dict[str, Any]], working: object
    ) -> tuple[list[dict[str, Any]], str]:
        observed.append([dict(message) for message in messages])
        return original_compact(messages, working)  # type: ignore[arg-type]

    controller.context.compact = capture  # type: ignore[method-assign]

    controller.run_turn("new request")

    assert observed
    assert observed[0][-1]["content"] != "new request"


def test_controller_restores_plan_and_available_skills(settings: Settings) -> None:
    skill_dir = settings.cwd / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: restore demo\n---\nRestored instructions.\n",
        encoding="utf-8",
    )
    skills = SkillRegistry(workspace=settings.cwd, user_root=settings.cwd / "user")
    skills.discover(include_repo=True)
    sessions = SessionStore(settings.data_dir)
    session_id = sessions.create({"workspace": str(settings.cwd.resolve())})
    sessions.append(
        session_id,
        "event",
        {"kind": "plan", "data": {"plan": [{"step": "restore", "status": "completed"}]}},
    )
    sessions.append(session_id, "event", {"kind": "skill", "data": {"name": 12}})
    sessions.append(session_id, "event", {"kind": "skill", "data": {"name": "missing"}})
    sessions.append(
        session_id,
        "event",
        {"kind": "skill", "data": {"name": "demo", "action": "disabled"}},
    )
    sessions.append(
        session_id,
        "event",
        {"kind": "skill", "data": {"name": "demo", "action": "enabled"}},
    )
    sessions.append(session_id, "event", {"kind": "skill", "data": {"name": "demo"}})
    controller = make_controller(
        settings,
        FakeModel([]),
        sessions=sessions,
        skills=skills,
        session_id=session_id,
    )
    assert controller.working.plan[0]["step"] == "restore"
    assert controller.working.active_skills == ["demo"]
    assert controller.skills is not None and controller.skills.skills["demo"].enabled

    controller.set_skill_enabled("demo", False)
    restored_skills = SkillRegistry(workspace=settings.cwd, user_root=settings.cwd / "user")
    restored_skills.discover(include_repo=True)
    restored = make_controller(
        settings,
        FakeModel([]),
        sessions=sessions,
        skills=restored_skills,
        session_id=session_id,
    )
    assert restored.skills is not None and not restored.skills.skills["demo"].enabled
    assert "demo" not in restored.working.active_skills


def test_controller_reports_bad_explicit_skill_and_internal_error(settings: Settings) -> None:
    skills = SkillRegistry(workspace=settings.cwd, user_root=settings.cwd / "user")
    skills.discover(include_repo=False)
    model = FakeModel(
        [
            [
                ModelStreamEvent(type="text_delta", text="done"),
                ModelStreamEvent(type="done", finish_reason="stop"),
            ]
        ]
    )
    controller = make_controller(settings, model, skills=skills)
    assert controller.run_turn("use $missing").exit_code == 0
    assert "could not be activated" in model.requests[0][0][0]["content"]

    class BrokenModel:
        model = "broken"

        def stream(
            self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
        ) -> Iterator[ModelStreamEvent]:
            raise RuntimeError("stream broke")
            yield ModelStreamEvent(type="done")

    events: list[Any] = []
    failed = make_controller(settings, BrokenModel(), events=events).run_turn("fail")
    assert failed.status is AgentState.FAILED
    assert "internal error: RuntimeError" in failed.reason
    assert any(event.kind is EventKind.ERROR for event in events)


def test_memory_validation_corruption_scoring_and_budgets(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = MemoryStore(data_dir=tmp_path / "data", workspace=workspace, enabled=True)
    with pytest.raises(MemoryError, match="1000"):
        store.remember(content="x" * 1001, session_id="s")
    with pytest.raises(MemoryError, match="secret"):
        store.remember(
            content="-----BEGIN " + "PRIVATE KEY-----\nsecret",
            session_id="s",
        )

    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{}", encoding="utf-8")
    assert store.list() == []
    store.path.write_text("not-json", encoding="utf-8")
    assert store.list() == []
    store.path.write_text('[{"kind":"invalid"}]', encoding="utf-8")
    assert store.list() == []

    low_score = store.propose(
        kind=MemoryKind.FACT,
        content="unrelated",
        evidence_session_id="s",
        confidence=0,
    )
    command = store.propose(
        kind=MemoryKind.COMMAND,
        content="Run pytest for tests/unit",
        evidence_session_id="s",
    )
    second = store.propose(
        kind=MemoryKind.CONSTRAINT,
        content="Keep pytest output concise",
        evidence_session_id="s",
    )
    store.approve(low_score)
    first_record = store.approve(command)
    store.approve(second)
    assert store.query("pytest", max_tokens=1) == []
    selected = store.query("pytest", paths=["tests/unit"], max_items=1, max_tokens=100)
    assert [item.id for item in selected] == [first_record.id]
    assert store.query("pytest", max_items=2, max_tokens=100)
    assert store.forget(first_record.id)
    assert not store.forget(first_record.id)
    assert all(item.id != first_record.id for item in store.query("pytest", max_tokens=100))


def test_approval_modes_and_command_input_rejections() -> None:
    with pytest.raises(ValueError, match="unknown permission"):
        ApprovalPolicy("unsafe")
    request = ApprovalRequest(action="write", subject="a", summary="write")
    read_only = ApprovalPolicy("read-only")
    assert read_only.decide(request) is ApprovalDecision.DENY
    denied = ApprovalPolicy("prompt", callback=lambda _: ApprovalDecision.DENY)
    assert denied.decide(request) is ApprovalDecision.DENY
    assert denied.denied

    policy = CommandPolicy()
    for command in ("", "bad\x00command", "first\nsecond"):
        assert not policy.classify(command).allowed


def test_workspace_path_errors_and_atomic_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_root = tmp_path / "file"
    file_root.write_text("x", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="not a directory"):
        WorkspacePaths(file_root)

    paths = WorkspacePaths(tmp_path)
    for value in ("", "bad\x00name"):
        with pytest.raises(PathSafetyError):
            paths.resolve(value)
    directory = tmp_path / "folder"
    directory.mkdir()
    with pytest.raises(PathSafetyError, match="not a file"):
        paths.resolve("folder", file_only=True)
    with pytest.raises(PathSafetyError, match="cannot resolve"):
        paths.resolve("x" * 40_000)

    target = tmp_path / "write.txt"
    before = set(tmp_path.iterdir())

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(path_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "content")
    assert set(tmp_path.iterdir()) == before


def test_process_tree_termination_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Child:
        def terminate(self) -> None:
            calls.append("child-terminate")

        def kill(self) -> None:
            calls.append("child-kill")

    class Parent:
        def children(self, recursive: bool) -> list[Child]:
            assert recursive
            return [Child()]

        def terminate(self) -> None:
            calls.append("parent-terminate")

        def wait(self, timeout: float) -> None:
            raise psutil.TimeoutExpired(timeout)

        def kill(self) -> None:
            calls.append("parent-kill")

    process = SimpleNamespace(pid=123, kill=lambda: calls.append("fallback-kill"))
    monkeypatch.setattr(command_module.psutil, "Process", lambda _pid: Parent())
    monkeypatch.setattr(
        command_module.psutil, "wait_procs", lambda children, timeout: ([], children)
    )
    command_module._terminate_tree(process)  # type: ignore[arg-type]
    assert calls == ["child-terminate", "child-kill", "parent-terminate", "parent-kill"]

    def missing_process(_pid: int) -> None:
        raise psutil.NoSuchProcess(123)

    monkeypatch.setattr(command_module.psutil, "Process", missing_process)
    command_module._terminate_tree(process)  # type: ignore[arg-type]
    assert calls[-1] == "fallback-kill"


def test_posix_subprocess_setup_is_platform_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    class Process:
        pid = 1

        def wait(self, timeout: int) -> int:
            captured["timeout"] = timeout
            return 0

    def popen(*args: Any, **kwargs: Any) -> Process:
        captured.update(kwargs)
        captured["argv"] = args[0]
        return Process()

    fake_os = SimpleNamespace(name="posix", environ={}, SEEK_END=os.SEEK_END)
    monkeypatch.setattr(command_module, "os", fake_os)
    monkeypatch.setattr(command_module.subprocess, "Popen", popen)
    result = command_module.run_subprocess("printf ok", cwd=tmp_path, timeout=0)
    assert result["exit_code"] == 0
    assert captured["argv"] == ["/bin/sh", "-c", "printf ok"]
    assert captured["start_new_session"] is True
    assert 0 < captured["timeout"] <= 1


def test_subprocess_interrupt_terminates_process_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits = 0
    terminated: list[int] = []

    class Process:
        pid = 42

        def wait(self, timeout: int) -> int:
            nonlocal waits
            waits += 1
            if waits == 1:
                raise KeyboardInterrupt
            assert timeout == 3
            return -1

    monkeypatch.setattr(command_module.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(
        command_module,
        "_terminate_tree",
        lambda process: terminated.append(process.pid),
    )
    with pytest.raises(KeyboardInterrupt):
        command_module.run_subprocess("cancel me", cwd=tmp_path, timeout=10)
    assert terminated == [42]
    assert waits == 2

    waits = 0

    def failed_termination(process: Process) -> None:
        assert process.pid == 42
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(command_module, "_terminate_tree", failed_termination)
    with pytest.raises(KeyboardInterrupt):
        command_module.run_subprocess("cancel me", cwd=tmp_path, timeout=10)
    assert waits == 1
