from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

import yaml


MAX_SKILL_BYTES = 64 * 1024
VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class SkillError(ValueError):
    pass


@dataclass
class SkillMetadata:
    name: str
    description: str
    source: str
    root: Path
    skill_file: Path
    sha256: str
    enabled: bool = True
    conflicts: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "sha256": self.sha256,
            "enabled": self.enabled,
            "conflicts": self.conflicts,
        }


def _frontmatter(path: Path) -> tuple[str, str]:
    size = path.stat().st_size
    if size > MAX_SKILL_BYTES:
        raise SkillError("SKILL.md exceeds 64 KiB")
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise SkillError("missing YAML frontmatter")
    match = re.match(r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", text, re.DOTALL)
    if not match:
        raise SkillError("unterminated YAML frontmatter")
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise SkillError("frontmatter must be a mapping")
    name = data.get("name")
    description = data.get("description")
    if not isinstance(name, str) or not VALID_NAME.fullmatch(name):
        raise SkillError("invalid or missing skill name")
    if not isinstance(description, str) or not description.strip():
        raise SkillError("invalid or missing skill description")
    return name, description.strip()


class SkillRegistry:
    def __init__(self, *, workspace: Path, user_root: Path | None = None) -> None:
        self.workspace = workspace.resolve()
        self.user_root = (user_root or (Path.home() / ".agents" / "skills")).resolve()
        self.skills: dict[str, SkillMetadata] = {}
        self.diagnostics: list[str] = []
        self.active: set[str] = set()

    def _discover_root(self, root: Path, source: str) -> list[SkillMetadata]:
        found: list[SkillMetadata] = []
        if not root.is_dir():
            return found
        for directory in sorted(root.iterdir()):
            path = directory / "SKILL.md"
            if not directory.is_dir() or not path.is_file():
                continue
            try:
                resolved_root = directory.resolve(strict=True)
                resolved_file = path.resolve(strict=True)
                resolved_file.relative_to(resolved_root)
                if source == "repo":
                    resolved_file.relative_to(self.workspace)
                name, description = _frontmatter(resolved_file)
                if name != directory.name:
                    raise SkillError("frontmatter name must match the directory name")
                digest = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
                found.append(
                    SkillMetadata(
                        name=name,
                        description=description,
                        source=source,
                        root=resolved_root,
                        skill_file=resolved_file,
                        sha256=digest,
                    )
                )
            except (OSError, UnicodeError, ValueError, SkillError) as exc:
                self.diagnostics.append(f"{path}: {exc}")
        return found

    def discover(self, *, include_repo: bool) -> list[SkillMetadata]:
        self.skills = {}
        self.diagnostics = []
        for meta in self._discover_root(self.user_root, "user"):
            self.skills[meta.name] = meta
        if include_repo:
            repo_root = self.workspace / ".agents" / "skills"
            for meta in self._discover_root(repo_root, "repo"):
                previous = self.skills.get(meta.name)
                if previous:
                    meta.conflicts.append(f"shadowed {previous.source} skill at {previous.root}")
                self.skills[meta.name] = meta
        self.active.intersection_update(self.skills)
        return list(self.skills.values())

    def catalog(self) -> list[dict[str, Any]]:
        return [self.skills[name].public() for name in sorted(self.skills)]

    def activate(self, name: str) -> str:
        meta = self.skills.get(name)
        if meta is None or not meta.enabled:
            raise SkillError(f"skill is unavailable: {name}")
        if meta.skill_file.stat().st_size > MAX_SKILL_BYTES:
            raise SkillError("SKILL.md changed and now exceeds 64 KiB")
        digest = hashlib.sha256(meta.skill_file.read_bytes()).hexdigest()
        if digest != meta.sha256:
            raise SkillError("SKILL.md changed; reload skills before activating it")
        content = meta.skill_file.read_text(encoding="utf-8")
        self.active.add(name)
        return content

    def read_resource(self, name: str, relative_path: str) -> str:
        if name not in self.active:
            raise SkillError(f"skill is not active: {name}")
        meta = self.skills[name]
        raw = Path(relative_path)
        if raw.is_absolute() or PureWindowsPath(relative_path).is_absolute():
            raise SkillError("skill resources must use relative paths")
        path = (meta.root / raw).resolve(strict=False)
        try:
            path.relative_to(meta.root)
        except ValueError as exc:
            raise SkillError("skill resource escapes its directory") from exc
        if not path.is_file():
            raise SkillError("skill resource is not a file")
        if path.stat().st_size > MAX_SKILL_BYTES:
            raise SkillError("skill resource exceeds 64 KiB")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SkillError("skill resource is not UTF-8 text") from exc

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name not in self.skills:
            raise SkillError(f"unknown skill: {name}")
        self.skills[name].enabled = enabled
        if not enabled:
            self.active.discard(name)
