from __future__ import annotations

import configparser
import hashlib
import json
import os
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from coding_agent.safety.paths import atomic_write_text, sha256_file

_AGENTS_NAME = "agents.md"
_MAX_AGENTS_BYTES = 64 * 1024
_MAX_AGENTS_TOTAL_BYTES = 256 * 1024
_IGNORED_RESOURCE_DIRS = {
    ".agents",
    ".coding-agent-data",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".test-runs",
    ".tmp-data",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "tmp",
    "venv",
}


def find_repository_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def _git_remote(root: Path) -> str:
    config_path = root / ".git" / "config"
    if not config_path.is_file():
        return ""
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except (OSError, configparser.Error):
        return ""
    for preferred in ('remote "origin"', *parser.sections()):
        if parser.has_option(preferred, "url"):
            return parser.get(preferred, "url")
    return ""


def project_id(workspace: Path) -> str:
    root = find_repository_root(workspace)
    identity = f"{root.as_posix().casefold()}\0{_git_remote(root)}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _confined_file(root: Path, candidate: Path) -> Path | None:
    if candidate.is_symlink() or not candidate.is_file():
        return None
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _directory_ignore_patterns(root: Path) -> tuple[str, ...]:
    ignore_file = _confined_file(root, root / ".gitignore")
    if ignore_file is None:
        return ()
    try:
        lines = ignore_file.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return ()
    patterns: list[str] = []
    for line in lines:
        value = line.strip()
        if not value or value.startswith(("#", "!")):
            continue
        patterns.append(value.removeprefix("/").removesuffix("/"))
    return tuple(pattern for pattern in patterns if pattern)


def _matches_directory_ignore(root: Path, path: Path, patterns: tuple[str, ...]) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(
        fnmatchcase(relative, pattern)
        or fnmatchcase(path.name, pattern)
        or fnmatchcase(relative, f"**/{pattern}")
        for pattern in patterns
    )


def _agents_files(root: Path) -> list[Path]:
    discovered: list[Path] = []
    ignore_patterns = _directory_ignore_patterns(root)
    for directory, names, files in os.walk(root, followlinks=False):
        retained: list[str] = []
        for name in names:
            path = Path(directory) / name
            if (
                name in _IGNORED_RESOURCE_DIRS
                or name.startswith(".test-tmp")
                or path.is_symlink()
                or (path / ".git").exists()
                or _matches_directory_ignore(root, path, ignore_patterns)
            ):
                continue
            retained.append(name)
        names[:] = retained
        for name in files:
            if name.casefold() != _AGENTS_NAME:
                continue
            agents_path = _confined_file(root, Path(directory) / name)
            if agents_path is not None:
                discovered.append(agents_path)
            if len(discovered) >= 256:
                return sorted(set(discovered))
    return sorted(set(discovered))


def _agents_by_directory(root: Path) -> dict[Path, Path]:
    """Choose one case-insensitive AGENTS.md file per directory."""

    selected: dict[Path, Path] = {}
    for path in _agents_files(root):
        current = selected.get(path.parent)
        if current is None or (path.name == "AGENTS.md" and current.name != "AGENTS.md"):
            selected[path.parent] = path
    return selected


def project_resource_files(workspace: Path) -> list[Path]:
    root = workspace.resolve()
    resources = _agents_files(root)
    config = _confined_file(root, root / "coding-agent.toml")
    if config is not None:
        resources.append(config)
    skill_root = root / ".agents" / "skills"
    if skill_root.is_dir():
        for directory, names, files in os.walk(skill_root, followlinks=False):
            names[:] = [name for name in names if not (Path(directory) / name).is_symlink()]
            for name in files:
                resolved = (Path(directory) / name).resolve()
                try:
                    resolved.relative_to(root)
                except ValueError:
                    continue
                if resolved.is_file():
                    resources.append(resolved)
                if len(resources) >= 1024:
                    break
            if len(resources) >= 1024:
                break
    return sorted(set(resources))


def resource_fingerprint(workspace: Path) -> str:
    digest = hashlib.sha256()
    root = workspace.resolve()
    for path in project_resource_files(root):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(sha256_file(path).encode())
    return digest.hexdigest()


@dataclass(frozen=True)
class TrustStatus:
    has_resources: bool
    trusted: bool
    fingerprint: str


class TrustManager:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "trusted-projects.json"

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def status(self, workspace: Path) -> TrustStatus:
        resources = project_resource_files(workspace)
        fingerprint = resource_fingerprint(workspace)
        record = self._load().get(project_id(workspace), {})
        trusted = bool(resources) and record.get("fingerprint") == fingerprint
        return TrustStatus(bool(resources), trusted, fingerprint)

    def trust_always(self, workspace: Path) -> None:
        records = self._load()
        records[project_id(workspace)] = {
            "root": str(workspace.resolve()),
            "fingerprint": resource_fingerprint(workspace),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.path, json.dumps(records, indent=2, ensure_ascii=False) + "\n")


def load_agents_instructions(workspace: Path, target: Path | None = None) -> str:
    """Load scoped AGENTS.md rules, including case-insensitive filename variants."""

    root = workspace.resolve()
    selected = _agents_by_directory(root)
    if target is None:
        root_path = selected.get(root)
        paths = [root_path] if root_path is not None else []
        nested_paths = sorted(
            (path for directory, path in selected.items() if directory != root),
            key=lambda path: path.as_posix().casefold(),
        )
    else:
        destination = target.resolve()
        try:
            relative = destination.relative_to(root)
        except ValueError as exc:
            raise ValueError("AGENTS.md target must stay inside the workspace") from exc
        directories = [root]
        cursor = root
        for part in relative.parts:
            cursor /= part
            directories.append(cursor)
        paths = [selected[directory] for directory in directories if directory in selected]
        nested_paths = []

    sections: list[str] = []
    total_bytes = 0
    for path in paths:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > _MAX_AGENTS_BYTES or total_bytes + size > _MAX_AGENTS_TOTAL_BYTES:
            continue
        try:
            content = path.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if not content:
            continue
        total_bytes += size
        relative_path = path.relative_to(root).as_posix()
        scope_dir = path.parent.relative_to(root).as_posix()
        scope = "entire workspace" if scope_dir == "." else f"{scope_dir}/**"
        sections.append(f"## {relative_path}\n\nScope: `{scope}`\n\n{content}")
    nested_index = ""
    if nested_paths:
        entries = [
            f"- `{path.relative_to(root).as_posix()}` applies to "
            f"`{path.parent.relative_to(root).as_posix()}/**`"
            for path in nested_paths
        ]
        nested_index = (
            "Nested rule files exist. Before changing a file in one of these scopes, read and "
            "apply the matching file:\n" + "\n".join(entries)
        )
    if not sections and not nested_index:
        return ""
    preamble = (
        "Repository AGENTS.md rules follow. A section applies only to its declared scope; "
        "deeper-scoped sections override broader ones when they conflict."
    )
    return preamble + "\n\n" + "\n\n".join([*sections, nested_index]).strip()
