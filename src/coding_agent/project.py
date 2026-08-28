from __future__ import annotations

import configparser
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coding_agent.safety.paths import atomic_write_text, sha256_file


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


def project_resource_files(workspace: Path) -> list[Path]:
    root = workspace.resolve()
    resources: list[Path] = []
    config = root / "coding-agent.toml"
    if config.is_file():
        resources.append(config)
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = [
            name for name in names if name != ".git" and not (Path(directory) / name).is_symlink()
        ]
        if "AGENTS.md" in files:
            resources.append((Path(directory) / "AGENTS.md").resolve())
        if len(resources) >= 256:
            break
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
    """Load AGENTS.md files from workspace down to a target directory."""

    root = workspace.resolve()
    destination = (target or root).resolve()
    try:
        relative = destination.relative_to(root)
    except ValueError as exc:
        raise ValueError("AGENTS.md target must stay inside the workspace") from exc
    directories = [root]
    cursor = root
    for part in relative.parts:
        cursor /= part
        directories.append(cursor)
    sections: list[str] = []
    for directory in directories:
        path = directory / "AGENTS.md"
        if not path.is_file():
            continue
        if path.stat().st_size > 64 * 1024:
            continue
        content = path.read_text(encoding="utf-8")
        sections.append(f"## {path.relative_to(root).as_posix()}\n\n{content.strip()}")
    return "\n\n".join(sections)
