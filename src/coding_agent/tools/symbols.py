from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from coding_agent.events import ToolResult
from coding_agent.tools.base import Tool, ToolContext

MAX_SOURCE_CHARS = 2 * 1024 * 1024
SUPPORTED_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".py",
    ".rs",
    ".ts",
    ".tsx",
}


class SymbolRecord(TypedDict):
    name: str
    qualified_name: str
    kind: str
    path: str
    line: int
    end_line: int


class ReferenceRecord(TypedDict):
    name: str
    path: str
    line: int
    column: int
    text: str


class PublicReferenceRecord(TypedDict):
    path: str
    line: int
    column: int
    text: str


@dataclass(frozen=True)
class IndexedFile:
    engine: Literal["python_ast", "lexical"]
    symbols: list[SymbolRecord]
    references: list[ReferenceRecord]


class _PythonSymbolVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.symbols: list[SymbolRecord] = []
        self.scope: list[tuple[str, str]] = []

    def _add(self, node: ast.stmt, name: str, kind: str) -> None:
        qualified = ".".join([*(item[0] for item in self.scope), name])
        self.symbols.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": kind,
                "path": self.path,
                "line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
            }
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add(node, node.name, "class")
        self.scope.append((node.name, "class"))
        self.generic_visit(node)
        self.scope.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        kind = "method" if self.scope and self.scope[-1][1] == "class" else "function"
        self._add(node, node.name, kind)
        self.scope.append((node.name, kind))
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def _attribute_column(line: str, name: str, start: int) -> int:
    marker = f".{name}"
    offset = line.find(marker, start)
    return (offset + 2) if offset >= 0 else (start + 1)


def _python_index(path: str, content: str) -> IndexedFile:
    tree = ast.parse(content)
    visitor = _PythonSymbolVisitor(path)
    visitor.visit(tree)
    lines = content.splitlines()
    references: list[ReferenceRecord] = []
    for node in ast.walk(tree):
        name: str | None = None
        line_number: int | None = None
        column = 0
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            name = node.id
            line_number = node.lineno
            column = node.col_offset + 1
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            name = node.attr
            line_number = node.lineno
            line_text = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
            column = _attribute_column(line_text, name, node.col_offset)
        if name is None or line_number is None:
            continue
        line_text = lines[line_number - 1] if line_number <= len(lines) else ""
        references.append(
            {
                "name": name,
                "path": path,
                "line": line_number,
                "column": column,
                "text": line_text[:500],
            }
        )
    references.sort(key=lambda item: (item["line"], item["column"], item["name"]))
    return IndexedFile(engine="python_ast", symbols=visitor.symbols, references=references)


_DECLARATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "type",
        re.compile(
            r"^\s*(?:export\s+)?(?:default\s+)?"
            r"(?P<kind>class|struct|interface|type|enum)\s+(?P<name>[A-Za-z_$][\w$]*)"
        ),
    ),
    (
        "function",
        re.compile(
            r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
            r"function\s+(?P<name>[A-Za-z_$][\w$]*)"
        ),
    ),
    (
        "function",
        re.compile(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+"
            r"(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
        ),
    ),
    (
        "function",
        re.compile(
            r"^\s*(?:pub\s+)?(?:static\s+)?(?:async\s+)?(?:fn|func)\s+"
            r"(?P<name>[A-Za-z_][\w]*)"
        ),
    ),
    (
        "cpp_function",
        re.compile(
            r"^\s*(?:(?:[A-Za-z_][\w:<>,~*&]*\s+)+)"
            r"(?:(?P<scope>[A-Za-z_][\w]*)::)?(?P<name>~?[A-Za-z_][\w]*)"
            r"\s*\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{"
        ),
    ),
)


def _lexical_index(path: str, content: str) -> IndexedFile:
    symbols: list[SymbolRecord] = []
    references: list[ReferenceRecord] = []
    declaration_positions: set[tuple[int, str]] = set()
    lines = content.splitlines()
    for line_number, line in enumerate(lines, 1):
        for fallback_kind, pattern in _DECLARATION_PATTERNS:
            match = pattern.search(line)
            if match is None:
                continue
            name = match.group("name")
            captured_kind = match.groupdict().get("kind")
            scope = match.groupdict().get("scope")
            if fallback_kind == "cpp_function":
                kind = "method" if scope else "function"
            else:
                kind = "type" if captured_kind == "type" else (captured_kind or fallback_kind)
            symbols.append(
                {
                    "name": name,
                    "qualified_name": f"{scope}.{name}" if scope else name,
                    "kind": kind,
                    "path": path,
                    "line": line_number,
                    "end_line": line_number,
                }
            )
            declaration_positions.add((line_number, name))
            break
    for line_number, line in enumerate(lines, 1):
        for match in re.finditer(r"[A-Za-z_$][\w$]*", line):
            name = match.group(0)
            if (line_number, name) in declaration_positions:
                continue
            references.append(
                {
                    "name": name,
                    "path": path,
                    "line": line_number,
                    "column": match.start() + 1,
                    "text": line[:500],
                }
            )
    return IndexedFile(engine="lexical", symbols=symbols, references=references)


class SymbolIndex:
    def __init__(self) -> None:
        self._cache: dict[Path, tuple[int, int, IndexedFile]] = {}

    def index(self, path: Path, display_path: str) -> IndexedFile:
        stat = path.stat()
        cached = self._cache.get(path)
        if cached is not None and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return cached[2]
        if stat.st_size > MAX_SOURCE_CHARS * 4:
            raise ValueError(f"source file is too large: {display_path}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"source file is not UTF-8: {display_path}") from exc
        if len(content) > MAX_SOURCE_CHARS:
            raise ValueError(f"source file is too large: {display_path}")
        indexed = (
            _python_index(display_path, content)
            if path.suffix.casefold() == ".py"
            else _lexical_index(display_path, content)
        )
        self._cache[path] = (stat.st_mtime_ns, stat.st_size, indexed)
        return indexed


class ListSymbolsArgs(BaseModel):
    path: str
    glob: str = "**/*"
    max_results: int = Field(default=200, ge=1, le=1000)


class SymbolSearchArgs(BaseModel):
    symbol: str = Field(min_length=1, max_length=200)
    path: str = "."
    glob: str = "**/*"
    max_results: int = Field(default=100, ge=1, le=500)


def _candidate_files(values_path: str, glob: str, context: ToolContext) -> list[Path]:
    root = context.workspace.resolve(values_path, must_exist=True)
    candidates = [root] if root.is_file() else list(root.glob(glob))
    return sorted(
        (
            path
            for path in candidates
            if path.is_file()
            and path.suffix.casefold() in SUPPORTED_SUFFIXES
            and ".git" not in path.parts
            and context.workspace.contains(path)
        ),
        key=context.workspace.display,
    )


class ListSymbolsTool(Tool):
    name = "list_symbols"
    description = "List classes, functions, methods, and types in a workspace source file or tree."
    args_model = ListSymbolsArgs

    def __init__(self, index: SymbolIndex) -> None:
        self.index = index

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = ListSymbolsArgs.model_validate(args)
        symbols: list[SymbolRecord] = []
        engines: set[str] = set()
        for path in _candidate_files(values.path, values.glob, context):
            indexed = self.index.index(path, context.workspace.display(path))
            engines.add(indexed.engine)
            symbols.extend(indexed.symbols)
            if len(symbols) >= values.max_results:
                break
        symbols = symbols[: values.max_results]
        engine = next(iter(engines)) if len(engines) == 1 else "mixed"
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"indexed {len(symbols)} symbols under {values.path}",
            data={"symbols": symbols, "engine": engine},
            truncated=len(symbols) == values.max_results,
        )


class FindDefinitionTool(Tool):
    name = "find_definition"
    description = "Find exact symbol definitions using the local source index."
    args_model = SymbolSearchArgs

    def __init__(self, index: SymbolIndex) -> None:
        self.index = index

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = SymbolSearchArgs.model_validate(args)
        definitions: list[SymbolRecord] = []
        for path in _candidate_files(values.path, values.glob, context):
            indexed = self.index.index(path, context.workspace.display(path))
            definitions.extend(
                item
                for item in indexed.symbols
                if item["name"] == values.symbol or item["qualified_name"] == values.symbol
            )
            if len(definitions) >= values.max_results:
                break
        definitions = definitions[: values.max_results]
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"found {len(definitions)} definitions for {values.symbol!r}",
            data={"definitions": definitions},
            truncated=len(definitions) == values.max_results,
        )


class FindReferencesTool(Tool):
    name = "find_references"
    description = "Find exact symbol references using the local source index."
    args_model = SymbolSearchArgs

    def __init__(self, index: SymbolIndex) -> None:
        self.index = index

    def execute(self, args: BaseModel, context: ToolContext) -> ToolResult:
        values = SymbolSearchArgs.model_validate(args)
        references: list[PublicReferenceRecord] = []
        for path in _candidate_files(values.path, values.glob, context):
            indexed = self.index.index(path, context.workspace.display(path))
            references.extend(
                {
                    "path": item["path"],
                    "line": item["line"],
                    "column": item["column"],
                    "text": item["text"],
                }
                for item in indexed.references
                if item["name"] == values.symbol
            )
            if len(references) >= values.max_results:
                break
        references = references[: values.max_results]
        return ToolResult(
            ok=True,
            code="OK",
            summary=f"found {len(references)} references for {values.symbol!r}",
            data={"references": references},
            truncated=len(references) == values.max_results,
        )
