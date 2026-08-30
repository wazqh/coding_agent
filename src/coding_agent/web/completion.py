from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from coding_agent.model_catalog import ModelCatalog
from coding_agent.ui.commands import COMMAND_SPECS

CompletionKind = Literal["command", "file", "skill", "argument"]
_TOKEN = re.compile(r"(?:^|\s)([/@$][^\s]*)$")


class CompletionItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: CompletionKind
    label: str = Field(min_length=1, max_length=4096)
    insert_text: str = Field(min_length=1, max_length=4096)
    description: str = Field(default="", max_length=1000)
    replace_start: int = Field(ge=0)
    replace_end: int = Field(ge=0)


class _Skills(Protocol):
    def catalog(self) -> list[dict[str, object]]: ...


def query_completions(
    *,
    text: str,
    cursor: int,
    workspace: Path,
    skills_provider: Callable[[], _Skills | None],
    model_catalog: ModelCatalog | None = None,
    limit: int = 40,
) -> list[CompletionItem]:
    """Return bounded, workspace-safe suggestions for the token at the cursor."""

    position = min(cursor, len(text))
    before = text[:position]
    match = _TOKEN.search(before)
    if match is None:
        return _argument_completions(
            before=before,
            position=position,
            model_catalog=model_catalog,
            limit=limit,
        )
    token = match.group(1)
    start = position - len(token)
    if token.startswith("/") and before[:start].strip() == "":
        normalized = token.casefold()
        return [
            CompletionItem(
                kind="command",
                label=spec.name,
                insert_text=spec.name,
                description=spec.description,
                replace_start=start,
                replace_end=position,
            )
            for spec in COMMAND_SPECS
            if spec.name.startswith(normalized)
        ][:limit]
    if token.startswith("$"):
        skills = skills_provider()
        if skills is None:
            return []
        prefix = token[1:].casefold()
        result: list[CompletionItem] = []
        for item in skills.catalog():
            name = str(item.get("name", ""))
            if not name.casefold().startswith(prefix) or item.get("enabled") is False:
                continue
            result.append(
                CompletionItem(
                    kind="skill",
                    label=f"${name}",
                    insert_text=f"${name}",
                    description=str(item.get("description", "")),
                    replace_start=start,
                    replace_end=position,
                )
            )
        return result[:limit]
    if token.startswith("@"):
        return _file_completions(
            workspace=workspace,
            token=token,
            start=start,
            end=position,
            limit=limit,
        )
    return []


def _argument_completions(
    *,
    before: str,
    position: int,
    model_catalog: ModelCatalog | None,
    limit: int,
) -> list[CompletionItem]:
    options: list[tuple[str, str]] = []
    prefix = ""
    if before.startswith("/steps "):
        prefix = before.removeprefix("/steps ")
        options = [(value, "下一轮生效") for value in ("12", "24", "40", "64", "100", "reset")]
    elif before.startswith("/permissions "):
        prefix = before.removeprefix("/permissions ")
        options = [
            ("prompt", "敏感操作前询问"),
            ("auto", "自动允许非破坏性操作"),
            ("read-only", "拒绝写入和命令"),
        ]
    elif before.startswith("/model use ") and model_catalog is not None:
        value = before.removeprefix("/model use ")
        provider, separator, prefix = value.partition(" ")
        if not separator:
            options = [(name, "模型服务商") for name in model_catalog.providers()]
        else:
            profile = model_catalog.config.providers.get(provider)
            if profile is not None:
                options = [(name, provider) for name in (profile.models or [profile.default_model])]
    elif before.startswith("/model "):
        prefix = before.removeprefix("/model ")
        options = [("use", "切换服务商或模型"), ("reload", "重新加载模型目录")]
    elif before.startswith("/memory "):
        prefix = before.removeprefix("/memory ")
        options = [
            ("list", "查看当前项目记忆"),
            ("on", "启用记忆注入"),
            ("off", "停用记忆注入"),
            ("remember", "添加已确认事实"),
            ("forget", "停用指定记忆"),
            ("clear confirm", "清空项目记忆，需二次确认"),
        ]
    elif before.startswith("/skills "):
        prefix = before.removeprefix("/skills ")
        options = [
            ("list", "浏览可用 Skills"),
            ("search", "搜索 Skills"),
            ("enable", "启用 Skill"),
            ("disable", "停用 Skill"),
            ("reload", "重新发现 Skills"),
        ]
    elif before.startswith("/raw "):
        prefix = before.removeprefix("/raw ")
        options = [("on", "展开工具原始结果"), ("off", "折叠工具原始结果")]
    else:
        return []
    start = position - len(prefix)
    return [
        CompletionItem(
            kind="argument",
            label=value,
            insert_text=value,
            description=description,
            replace_start=start,
            replace_end=position,
        )
        for value, description in options
        if value.casefold().startswith(prefix.casefold())
    ][:limit]


def _file_completions(
    *,
    workspace: Path,
    token: str,
    start: int,
    end: int,
    limit: int,
) -> list[CompletionItem]:
    root = workspace.resolve(strict=True)
    prefix = token[1:].casefold()
    result: list[CompletionItem] = []
    for directory, names, files in os.walk(root, followlinks=False):
        base = Path(directory)
        names[:] = [name for name in names if name != ".git" and not (base / name).is_symlink()]
        for name in files:
            path = base / name
            if path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if prefix not in relative.casefold():
                continue
            result.append(
                CompletionItem(
                    kind="file",
                    label=f"@{relative}",
                    insert_text=f"@{relative}",
                    description="工作区文件",
                    replace_start=start,
                    replace_end=end,
                )
            )
            if len(result) >= limit:
                return result
    return result
