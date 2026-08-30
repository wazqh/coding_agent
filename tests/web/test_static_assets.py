from __future__ import annotations

import re
import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

REPOSITORY_ROOT = Path(__file__).parents[2]
STATIC_PREFIX = "coding_agent/web/static/"


def _build_distribution(tmp_path: Path, target: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            target,
            "--no-isolation",
            "--outdir",
            str(tmp_path),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_wheel_contains_only_production_web_assets(tmp_path: Path) -> None:
    _build_distribution(tmp_path, "--wheel")
    wheel = next(tmp_path.glob("*.whl"))

    with ZipFile(wheel) as archive:
        names = set(archive.namelist())
        static_names = {name for name in names if name.startswith(STATIC_PREFIX)}
        index = archive.read(f"{STATIC_PREFIX}index.html").decode("utf-8")
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")

    assert re.search(rf"{STATIC_PREFIX}assets/index-[\w-]+\.js", "\n".join(names))
    assert re.search(rf"{STATIC_PREFIX}assets/index-[\w-]+\.css", "\n".join(names))
    assert "NotoSansSC" in "\n".join(static_names)
    assert "jetbrains-mono" in "\n".join(static_names)
    assert all(not name.endswith((".map", ".ts", ".tsx")) for name in static_names)
    assert all("node_modules" not in name for name in names)
    forbidden_secret_names = {
        ".env",
        ".env.local",
        "provider-credentials.json",
        "credentials.json",
    }
    assert all(Path(name).name.casefold() not in forbidden_secret_names for name in names)
    assert all(".test." not in name for name in static_names)
    assert re.search(r"/assets/index-[\w-]+\.js", index)
    assert re.search(r"/assets/index-[\w-]+\.css", index)
    assert re.search(r"Requires-Dist: uvicorn\[standard\].*extra == ['\"]web['\"]", metadata)


def test_sdist_excludes_local_test_and_frontend_build_data(tmp_path: Path) -> None:
    _build_distribution(tmp_path, "--sdist")
    archive_path = next(tmp_path.glob("*.tar.gz"))

    with tarfile.open(archive_path, "r:gz") as archive:
        names = [Path(name).parts[1:] for name in archive.getnames()]

    forbidden_roots = {
        ".pytest_cache",
        ".test-runs",
        "dist",
        "node_modules",
        "playwright-report",
        "test-results",
    }
    assert all(
        parts
        and parts[0] not in forbidden_roots
        and not parts[0].startswith((".test-tmp", "pytest-cache-files-"))
        and "node_modules" not in parts
        for parts in names
    )
