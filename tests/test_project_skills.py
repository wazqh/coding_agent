from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.project import (
    TrustManager,
    load_agents_instructions,
    project_id,
    project_resource_files,
    resource_fingerprint,
)
from coding_agent.skills import SkillError, SkillRegistry


def write_skill(root: Path, name: str, description: str = "Useful skill") -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# Instructions\nRead carefully.\n",
        encoding="utf-8",
    )
    return path


def test_trust_invalidates_on_resource_change(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("First", encoding="utf-8")
    manager = TrustManager(tmp_path / "data")
    assert manager.status(workspace).has_resources
    assert not manager.status(workspace).trusted
    before = resource_fingerprint(workspace)
    manager.trust_always(workspace)
    assert manager.status(workspace).trusted
    (workspace / "AGENTS.md").write_text("Second", encoding="utf-8")
    assert resource_fingerprint(workspace) != before
    assert not manager.status(workspace).trusted
    assert len(project_id(workspace)) == 24


def test_trust_fingerprints_skill_resources(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    skill = write_skill(workspace / ".agents" / "skills", "demo")
    resource = skill.parent / "guide.txt"
    resource.write_text("first", encoding="utf-8")
    manager = TrustManager(tmp_path / "data")
    manager.trust_always(workspace)
    assert manager.status(workspace).trusted
    resource.write_text("second", encoding="utf-8")
    assert not manager.status(workspace).trusted


def test_agents_hierarchy_and_boundary(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("root rule", encoding="utf-8")
    nested = tmp_path / "src" / "pkg"
    nested.mkdir(parents=True)
    (tmp_path / "src" / "AGENTS.md").write_text("src rule", encoding="utf-8")
    content = load_agents_instructions(tmp_path, nested)
    assert content.index("root rule") < content.index("src rule")
    assert "Scope: `entire workspace`" in content
    assert "Scope: `src/**`" in content
    root_scopes = load_agents_instructions(tmp_path)
    assert "root rule" in root_scopes
    assert "src rule" not in root_scopes
    assert "`src/AGENTS.md` applies to `src/**`" in root_scopes
    with pytest.raises(ValueError):
        load_agents_instructions(tmp_path, tmp_path.parent)
    assert (tmp_path / "src" / "AGENTS.md") in project_resource_files(tmp_path)


def test_agents_filename_is_case_insensitive(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.MD"
    path.write_text("uppercase extension rule", encoding="utf-8")

    content = load_agents_instructions(tmp_path)

    assert "uppercase extension rule" in content
    assert path.resolve() in project_resource_files(tmp_path)


def test_agents_discovery_ignores_temp_and_nested_repositories(tmp_path: Path) -> None:
    root_agents = tmp_path / "AGENTS.md"
    root_agents.write_text("root", encoding="utf-8")
    temporary = tmp_path / ".test-tmp-run"
    nested_repo = tmp_path / "vendor"
    ignored = tmp_path / "scratch-generated"
    temporary.mkdir()
    nested_repo.mkdir()
    ignored.mkdir()
    (nested_repo / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("scratch-*/\n", encoding="utf-8")
    (temporary / "AGENTS.md").write_text("temporary", encoding="utf-8")
    (nested_repo / "AGENTS.md").write_text("nested repository", encoding="utf-8")
    (ignored / "AGENTS.md").write_text("ignored output", encoding="utf-8")

    content = load_agents_instructions(tmp_path)
    resources = project_resource_files(tmp_path)

    assert "root" in content
    assert "temporary" not in content
    assert "nested repository" not in content
    assert "ignored output" not in content
    assert resources == [root_agents]


def test_skill_lazy_loading_conflict_and_resources(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    user = tmp_path / "user-skills"
    workspace.mkdir()
    user_path = write_skill(user, "test-fix", "user version")
    repo_path = write_skill(workspace / ".agents" / "skills", "test-fix", "repo version")
    (repo_path.parent / "guide.txt").write_text("guide", encoding="utf-8")
    marker = repo_path.parent / "ran.txt"
    (repo_path.parent / "script.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n", encoding="utf-8"
    )
    registry = SkillRegistry(workspace=workspace, user_root=user)
    catalog = registry.discover(include_repo=True)
    assert len(catalog) == 1
    meta = registry.skills["test-fix"]
    assert meta.source == "repo" and meta.conflicts
    assert "# Instructions" not in str(meta.public())
    content = registry.activate("test-fix")
    assert "# Instructions" in content
    assert not marker.exists(), "loading a skill must never execute scripts"
    assert registry.read_resource("test-fix", "guide.txt") == "guide"
    with pytest.raises(SkillError):
        registry.read_resource("test-fix", "../outside.txt")
    assert user_path.exists()


def test_invalid_skill_and_hash_change_are_quarantined(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    root = workspace / ".agents" / "skills"
    bad = root / "bad"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text("no frontmatter", encoding="utf-8")
    changed = write_skill(root, "changed")
    registry = SkillRegistry(workspace=workspace, user_root=tmp_path / "none")
    registry.discover(include_repo=True)
    assert registry.diagnostics
    changed.write_text(changed.read_text(encoding="utf-8") + "changed", encoding="utf-8")
    with pytest.raises(SkillError, match="changed"):
        registry.activate("changed")


def test_user_skill_disable_and_repo_opt_out(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    user = tmp_path / "user"
    write_skill(user, "user-only")
    write_skill(workspace / ".agents" / "skills", "repo-only")
    registry = SkillRegistry(workspace=workspace, user_root=user)
    registry.discover(include_repo=False)
    assert set(registry.skills) == {"user-only"}
    registry.set_enabled("user-only", False)
    with pytest.raises(SkillError, match="unavailable"):
        registry.activate("user-only")
