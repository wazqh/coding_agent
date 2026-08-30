from __future__ import annotations

from pathlib import Path

from coding_agent.safety.paths import PathSafetyError, WorkspacePaths

MAX_PREVIEW_BYTES = 2 * 1024 * 1024

_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".css": "css",
    ".go": "go",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".py": "python",
    ".rs": "rust",
    ".sh": "shell",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class PreviewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WorkspacePreview:
    """Read small UTF-8 text files through the workspace path boundary."""

    def __init__(self, workspace: Path) -> None:
        self.paths = WorkspacePaths(workspace)

    def read(self, raw_path: str) -> dict[str, object]:
        try:
            path = self.paths.resolve(raw_path, file_only=True)
        except PathSafetyError as exc:
            raise PreviewError("unsafe_path", str(exc)) from exc
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise PreviewError("unreadable_file", "file cannot be inspected") from exc
        if size > MAX_PREVIEW_BYTES:
            raise PreviewError("file_too_large", "file exceeds the 2 MiB preview limit")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise PreviewError("unreadable_file", "file cannot be inspected") from exc
        if len(content) > MAX_PREVIEW_BYTES:
            raise PreviewError("file_too_large", "file exceeds the 2 MiB preview limit")
        if b"\x00" in content:
            raise PreviewError("binary_file", "binary files cannot be previewed")
        try:
            text = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise PreviewError("invalid_utf8", "file is not valid UTF-8 text") from exc
        return {
            "path": self.paths.display(path),
            "language": _LANGUAGES.get(path.suffix.lower(), "text"),
            "size": len(content),
            "text": text,
        }
