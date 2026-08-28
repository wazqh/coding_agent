from __future__ import annotations

from conftest import FakeModel

from coding_agent.config import Settings
from coding_agent.controller import AgentController
from coding_agent.events import EventKind, ModelStreamEvent, ToolCall
from coding_agent.memory import MemoryStore
from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.session import SessionStore
from coding_agent.skills import SkillRegistry
from coding_agent.tools.registry import default_registry


def _text(value: str) -> list[ModelStreamEvent]:
    return [
        ModelStreamEvent(type="text_delta", text=value),
        ModelStreamEvent(type="done", finish_reason="stop"),
    ]


def _controller(
    settings: Settings,
    model: FakeModel,
    memory: MemoryStore,
    skills: SkillRegistry,
    events: list,
) -> AgentController:
    return AgentController(
        settings=settings,
        model=model,  # type: ignore[arg-type]
        tools=default_registry(),
        sessions=SessionStore(settings.data_dir),
        approval=ApprovalPolicy("auto"),
        memory=memory,
        skills=skills,
        agents_instructions="Run repository checks before completion.",
        event_sink=events.append,
    )


def test_controller_injects_only_approved_memory_and_explicit_skill(settings: Settings) -> None:
    skill_dir = settings.cwd / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: inspect Python changes\n---\nAlways inspect first.\n",
        encoding="utf-8",
    )
    skills = SkillRegistry(workspace=settings.cwd, user_root=settings.cwd / "user")
    skills.discover(include_repo=True)
    memory = MemoryStore(data_dir=settings.data_dir, workspace=settings.cwd, enabled=True)
    pending = memory.propose(
        kind="fact",
        content="A pending memory must not be injected",
        evidence_session_id="old",
    )
    memory.remember(content="Run pytest -q for this project", session_id="old")
    model = FakeModel([_text("done")])
    events: list = []
    controller = _controller(settings, model, memory, skills, events)
    result = controller.run_turn("$demo run pytest for @tests/test_demo.py")
    assert result.exit_code == 0
    system = model.requests[0][0][0]["content"]
    assert "Run repository checks" in system
    assert "Run pytest -q" in system
    assert pending.content not in system
    assert "Always inspect first" in system
    assert any(event.kind is EventKind.SKILL for event in events)


def test_model_can_activate_discovered_skill_lazily(settings: Settings) -> None:
    skill_dir = settings.cwd / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo workflow\n---\nFollow the demo workflow.\n",
        encoding="utf-8",
    )
    skills = SkillRegistry(workspace=settings.cwd, user_root=settings.cwd / "user")
    skills.discover(include_repo=True)
    memory = MemoryStore(data_dir=settings.data_dir, workspace=settings.cwd, enabled=False)
    model = FakeModel(
        [
            [
                ModelStreamEvent(
                    type="tool_calls",
                    tool_calls=[
                        ToolCall(id="skill", name="activate_skill", arguments={"name": "demo"})
                    ],
                ),
                ModelStreamEvent(type="done", finish_reason="tool_calls"),
            ],
            _text("activated"),
        ]
    )
    controller = _controller(settings, model, memory, skills, [])
    result = controller.run_turn("use a suitable workflow")
    assert result.exit_code == 0
    assert controller.working.active_skills == ["demo"]
    tool_messages = [message for message in model.requests[1][0] if message.get("role") == "tool"]
    assert "Follow the demo workflow" in tool_messages[-1]["content"]
