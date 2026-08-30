from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.web.preview import PreviewError, WorkspacePreview


def test_preview_accepts_bounded_utf8_workspace_text(tmp_path: Path) -> None:
    source = tmp_path / "src" / "demo.py"
    source.parent.mkdir()
    expected = "print('你好')\n"
    source.write_bytes(expected.encode("utf-8"))

    preview = WorkspacePreview(tmp_path).read("src/demo.py")

    assert preview == {
        "path": "src/demo.py",
        "language": "python",
        "size": len(expected.encode()),
        "text": expected,
    }


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", r"C:\Windows\win.ini"])
def test_preview_rejects_traversal_and_absolute_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(PreviewError) as caught:
        WorkspacePreview(tmp_path).read(path)

    assert caught.value.code == "unsafe_path"


def test_preview_rejects_workspace_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "escape.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this Windows host")

    with pytest.raises(PreviewError) as caught:
        WorkspacePreview(tmp_path).read("escape.txt")

    assert caught.value.code == "unsafe_path"


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"text\x00binary", "binary_file"),
        (b"\xff\xfe\xfa", "invalid_utf8"),
        (b"x" * (2 * 1024 * 1024 + 1), "file_too_large"),
    ],
    ids=["binary", "invalid-utf8", "too-large"],
)
def test_preview_rejects_unsafe_content(tmp_path: Path, content: bytes, code: str) -> None:
    (tmp_path / "payload.txt").write_bytes(content)

    with pytest.raises(PreviewError) as caught:
        WorkspacePreview(tmp_path).read("payload.txt")

    assert caught.value.code == code
