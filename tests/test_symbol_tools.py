from __future__ import annotations

from pathlib import Path

from coding_agent.safety.approval import ApprovalPolicy
from coding_agent.safety.paths import WorkspacePaths
from coding_agent.tools.base import ToolContext, WorkingState
from coding_agent.tools.registry import default_registry


def _context(root: Path) -> ToolContext:
    return ToolContext(
        workspace=WorkspacePaths(root),
        approval=ApprovalPolicy("auto", interactive=True),
        session_id="a" * 24,
        turn_id="turn",
        working=WorkingState(),
    )


def test_python_symbol_tools_find_outline_definition_and_references(tmp_path: Path) -> None:
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir()
    source.write_text(
        "class Greeter:\n"
        "    def greet(self, name: str) -> str:\n"
        "        return helper(name)\n"
        "\n"
        "def helper(value: str) -> str:\n"
        "    return value.upper()\n"
        "\n"
        "def run() -> str:\n"
        "    return Greeter().greet('Forge')\n",
        encoding="utf-8",
    )
    registry = default_registry()
    context = _context(tmp_path)

    outline = registry.execute("list_symbols", {"path": "src/sample.py"}, context)
    definitions = registry.execute(
        "find_definition",
        {"symbol": "helper", "path": "src"},
        context,
    )
    references = registry.execute(
        "find_references",
        {"symbol": "greet", "path": "src"},
        context,
    )

    assert outline.ok
    assert outline.data["engine"] == "python_ast"
    assert outline.data["symbols"] == [
        {
            "name": "Greeter",
            "qualified_name": "Greeter",
            "kind": "class",
            "path": "src/sample.py",
            "line": 1,
            "end_line": 3,
        },
        {
            "name": "greet",
            "qualified_name": "Greeter.greet",
            "kind": "method",
            "path": "src/sample.py",
            "line": 2,
            "end_line": 3,
        },
        {
            "name": "helper",
            "qualified_name": "helper",
            "kind": "function",
            "path": "src/sample.py",
            "line": 5,
            "end_line": 6,
        },
        {
            "name": "run",
            "qualified_name": "run",
            "kind": "function",
            "path": "src/sample.py",
            "line": 8,
            "end_line": 9,
        },
    ]
    assert definitions.data["definitions"] == [outline.data["symbols"][2]]
    assert references.data["references"] == [
        {
            "path": "src/sample.py",
            "line": 9,
            "column": 22,
            "text": "    return Greeter().greet('Forge')",
        }
    ]


def test_typescript_outline_uses_a_lightweight_lexical_index(tmp_path: Path) -> None:
    source = tmp_path / "ui.ts"
    source.write_text(
        "export interface Task { id: string }\n"
        "export class Runner { run(): void {} }\n"
        "export function createTask(): Task { return { id: '1' } }\n"
        "export const formatTask = (task: Task) => task.id\n",
        encoding="utf-8",
    )
    registry = default_registry()
    context = _context(tmp_path)

    outline = registry.execute("list_symbols", {"path": "ui.ts"}, context)
    definition = registry.execute(
        "find_definition",
        {"symbol": "formatTask", "path": "."},
        context,
    )

    assert outline.ok
    assert outline.data["engine"] == "lexical"
    assert [(item["name"], item["kind"], item["line"]) for item in outline.data["symbols"]] == [
        ("Task", "interface", 1),
        ("Runner", "class", 2),
        ("createTask", "function", 3),
        ("formatTask", "function", 4),
    ]
    assert definition.data["definitions"][0]["path"] == "ui.ts"
    assert definition.data["definitions"][0]["line"] == 4


def test_cpp_outline_recognizes_types_and_function_definitions(tmp_path: Path) -> None:
    source = tmp_path / "sample.cpp"
    source.write_text(
        "struct Entry { int value; };\n"
        "int add(int left, int right) { return left + right; }\n"
        'std::string Runner::name() const { return "forge"; }\n',
        encoding="utf-8",
    )
    registry = default_registry()

    outline = registry.execute("list_symbols", {"path": "sample.cpp"}, _context(tmp_path))

    assert [(item["qualified_name"], item["kind"]) for item in outline.data["symbols"]] == [
        ("Entry", "struct"),
        ("add", "function"),
        ("Runner.name", "method"),
    ]


def test_symbol_tools_stay_inside_the_workspace(tmp_path: Path) -> None:
    registry = default_registry()
    context = _context(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("secret = True\n", encoding="utf-8")

    result = registry.execute("list_symbols", {"path": f"../{outside.name}"}, context)

    assert result.code == "TOOL_ERROR"
    assert "escapes workspace" in result.summary
