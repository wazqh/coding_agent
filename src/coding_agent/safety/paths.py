from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path, PureWindowsPath


class PathSafetyError(ValueError):
    pass


class WorkspacePaths:
    def __init__(self, workspace: Path | str) -> None:
        self.root = Path(workspace).resolve(strict=True)
        if not self.root.is_dir():
            raise PathSafetyError(f"workspace is not a directory: {self.root}")

    def resolve(
        self,
        raw_path: str,
        *,
        must_exist: bool = True,
        file_only: bool = False,
    ) -> Path:
        if not raw_path or "\x00" in raw_path:
            raise PathSafetyError("path is empty or contains NUL")
        supplied = Path(raw_path)
        if supplied.is_absolute() or PureWindowsPath(raw_path).is_absolute():
            raise PathSafetyError("absolute paths are not allowed")
        try:
            resolved = (self.root / supplied).resolve(strict=must_exist)
        except OSError as exc:
            raise PathSafetyError(f"cannot resolve path: {raw_path}") from exc
        if not self.contains(resolved):
            raise PathSafetyError(f"path escapes workspace: {raw_path}")
        if file_only and resolved.exists() and not resolved.is_file():
            raise PathSafetyError(f"path is not a file: {raw_path}")
        return resolved

    def contains(self, path: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(self.root)
            return True
        except ValueError:
            return False

    def display(self, path: Path) -> str:
        return path.resolve(strict=False).relative_to(self.root).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = path.stat().st_mode if path.exists() else None
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if previous_mode is not None:
            os.chmod(temp_path, previous_mode)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

