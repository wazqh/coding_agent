from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from coding_agent.events import ToolResult
from coding_agent.safety.paths import PathSafetyError
from coding_agent.tools.base import Tool, ToolContext
from coding_agent.tools.command import RunCommandTool
from coding_agent.tools.filesystem import (
    EditFileTool,
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
    WriteFileTool,
)
from coding_agent.tools.plan import UpdatePlanTool
from coding_agent.tools.skill import ActivateSkillTool, ReadSkillResourceTool
from coding_agent.tools.symbols import (
    FindDefinitionTool,
    FindReferencesTool,
    ListSymbolsTool,
    SymbolIndex,
)
from coding_agent.tools.verification import RegisterVerificationTool, RunVerifyTool


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def execute(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, code="UNKNOWN_TOOL", summary=f"unknown tool: {name}")
        try:
            args = tool.args_model.model_validate(arguments)
            return tool.execute(args, context)
        except ValidationError as exc:
            return ToolResult(
                ok=False,
                code="INVALID_ARGUMENTS",
                summary="tool arguments failed validation",
                # Pydantic's default context can retain the original ValueError.
                # Tool observations are persisted and sent through JSON, so keep
                # validation diagnostics strictly data-only.
                data={"errors": exc.errors(include_url=False, include_context=False)},
            )
        except (PathSafetyError, OSError, ValueError) as exc:
            return ToolResult(ok=False, code="TOOL_ERROR", summary=str(exc))
        except Exception as exc:  # keep an unexpected tool bug inside the observation loop
            return ToolResult(
                ok=False,
                code="INTERNAL_TOOL_ERROR",
                summary=f"{type(exc).__name__}: {exc}",
            )


def default_registry() -> ToolRegistry:
    symbol_index = SymbolIndex()
    return ToolRegistry(
        [
            UpdatePlanTool(),
            ListFilesTool(),
            ReadFileTool(),
            SearchTextTool(),
            ListSymbolsTool(symbol_index),
            FindDefinitionTool(symbol_index),
            FindReferencesTool(symbol_index),
            EditFileTool(),
            WriteFileTool(),
            RunCommandTool(),
            RegisterVerificationTool(),
            RunVerifyTool(),
            ActivateSkillTool(),
            ReadSkillResourceTool(),
        ]
    )
