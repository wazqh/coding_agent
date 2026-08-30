from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.model_catalog import ModelCatalog
from coding_agent.web.completion import query_completions


class _Skills:
    def catalog(self) -> list[dict[str, object]]:
        return [
            {"name": "review", "description": "Review code", "enabled": True},
            {"name": "retired", "description": "Disabled", "enabled": False},
        ]


def _query(
    text: str,
    workspace: Path,
    *,
    catalog: ModelCatalog | None = None,
    limit: int = 40,
):
    return query_completions(
        text=text,
        cursor=len(text),
        workspace=workspace,
        skills_provider=lambda: _Skills(),
        model_catalog=catalog,
        limit=limit,
    )


def test_completes_commands_skills_and_workspace_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "secret").write_text("ignored", encoding="utf-8")

    commands = _query("/mo", tmp_path)
    skills = _query("use $re", tmp_path)
    files = _query("inspect @demo", tmp_path)

    assert [item.label for item in commands] == ["/model"]
    assert [item.label for item in skills] == ["$review"]
    assert [item.label for item in files] == ["@src/demo.py"]
    assert files[0].replace_start == len("inspect ")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/steps 4", ["40"]),
        ("/permissions r", ["read-only"]),
        ("/model r", ["reload"]),
        ("/memory o", ["on", "off"]),
        ("/skills re", ["reload"]),
        ("/raw o", ["on", "off"]),
    ],
)
def test_completes_management_arguments(text: str, expected: list[str], tmp_path: Path) -> None:
    assert [item.label for item in _query(text, tmp_path)] == expected


def test_completes_provider_and_model_arguments(tmp_path: Path) -> None:
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text(
        """
default_provider = "demo"

[providers.demo]
base_url = "https://example.test/v1"
api_key_env = "DEMO_API_KEY"
default_model = "fast"
models = ["fast", "strong"]
""".lstrip(),
        encoding="utf-8",
    )
    catalog = ModelCatalog(path=catalog_path, environ={})

    providers = _query("/model use d", tmp_path, catalog=catalog)
    models = _query("/model use demo s", tmp_path, catalog=catalog)

    assert [item.label for item in providers] == ["demo"]
    assert [item.label for item in models] == ["strong"]


def test_completion_is_bounded_and_returns_empty_without_a_supported_token(tmp_path: Path) -> None:
    assert _query("plain text", tmp_path) == []
    assert (
        query_completions(
            text="$r",
            cursor=2,
            workspace=tmp_path,
            skills_provider=lambda: None,
            limit=1,
        )
        == []
    )
