# Forge Coding Agent

An original Python 3.11+ CLI coding-agent runtime. The repository is being delivered in tested,
independently reviewable modules; installation and end-user commands will be enabled with the CLI
module.

Implemented modules:

- validated configuration with explicit precedence and environment-only API credentials;
- shared agent event and tool-result contracts;
- OpenAI-compatible streaming adapter with fragmented function-call assembly and bounded retry.
- workspace-confined file tools with hash-guarded atomic edits and centralized approvals;
- screened command execution with secret stripping, timeout, process-tree termination, and bounded output;
- a local model-tool-observation loop with visible plans, loop guards, budgets, cancellation, and JSONL sessions;
- resumable conversation state and deterministic context compaction that preserves the original transcript.
- opt-in, approved project memory with secret filtering, deterministic retrieval, and project isolation;
- hash-invalidated trust for project configuration, hierarchical AGENTS.md instructions, and repository skills;
- user/repository SKILL.md discovery, conflict diagnostics, lazy activation, and confined resource reads.

The interactive CLI/TUI is available through the package entry points described below.

## CLI

Install the package in Python 3.11 or newer, provide credentials through the environment, and start
the scrolling terminal interface:

    python -m pip install -e .
    set OPENAI_API_KEY=...
    coding-agent --cwd .

On macOS or Linux, use export instead of set. Credentials are never accepted as CLI arguments or
from the project TOML file. If Windows cannot find the console command after a user installation,
add the Python-versioned user Scripts directory beside the user site-packages directory to PATH;
the module entry point works independently of PATH.

Single-turn and session commands are also available:

    coding-agent run "inspect the failing tests" --cwd . --output jsonl
    coding-agent sessions --output table
    coding-agent resume SESSION_ID --cwd .

The TUI uses normal terminal scrollback rather than an alternate screen. Enter submits; Ctrl+J or
Alt+Enter inserts a newline; Ctrl+G opens the configured editor. Slash commands, dollar-prefixed
skills, and at-prefixed workspace paths support completion.

The implementation does not use an agent framework or a hosted code-execution/file service.
