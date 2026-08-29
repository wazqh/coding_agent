# Forge Coding Agent

Forge is an original Python 3.11+ command-line coding agent. It combines a scrolling professional
terminal UI with a locally controlled model-tool-observation loop, resumable sessions, approved
project memory, lazy `SKILL.md` workflows, and strict workspace safety. It does not use an agent
framework, hosted code execution, or a remote file service.

## Install and start

Create a virtual environment, install the package, and provide credentials only through the
environment:

```text
python -m pip install -e .

# PowerShell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_BASE_URL = "https://your-compatible-endpoint/v1"
$env:CODING_AGENT_MODEL = "your-model"

python -m coding_agent --cwd .
coding-agent --cwd .
```

`OPENAI_BASE_URL` and `CODING_AGENT_MODEL` are optional. API keys are not accepted as CLI
arguments, project configuration, or saved memory. On Windows, `python -m coding_agent` works even
when the user-level Python Scripts directory is not on `PATH`.

### Multiple OpenAI-compatible providers

Create `models.toml` in the Forge user data directory (the directory selected by
`CODING_AGENT_DATA_DIR`, or the platform default) to reuse provider profiles across projects. The
file stores only the environment-variable name that contains each API key; secret values are never
written to the catalog or active-selection state.

```toml
default_provider = "gemini"

[providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key_env = "GEMINI_API_KEY"
default_model = "gemini-3.7-flash"
models = ["gemini-3.7-flash", "gemini-3.1-pro"]
compatibility = "gemini"

[providers.deepseek]
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"
default_model = "deepseek-chat"
models = ["deepseek-chat", "deepseek-reasoner"]
```

Use `/model use PROVIDER [MODEL_ID]` to change provider, `/model MODEL_ID` to change the
model within the current provider, and `/model reload` after editing the catalog. The active
provider and model are restored on the next launch. `--model` temporarily overrides the restored
model while retaining the selected provider. Without `models.toml`, the existing `OPENAI_API_KEY`,
`OPENAI_BASE_URL`, and `CODING_AGENT_MODEL` flow remains unchanged.

### Gemini through the OpenAI-compatible endpoint

Gemini keys can be used without installing a second SDK. Set all three variables in the same
PowerShell session:

```powershell
$env:OPENAI_API_KEY = "YOUR_GEMINI_API_KEY"
$env:OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
$env:CODING_AGENT_MODEL = "gemini-3.7-flash"

python -m coding_agent run "Read README.md and summarize it in three sentences" `
  --cwd . --output rich --permissions read-only --trust-project
```

The adapter consumes raw Chat Completions chunks because some compatible endpoints omit the tool
call indexes required by the OpenAI SDK's high-level stream accumulator. Gemini tool-call thought
signatures are preserved and returned in `extra_content.google.thought_signature` as required by
the [Gemini OpenAI compatibility documentation](https://ai.google.dev/gemini-api/docs/openai) and
[thought-signature guide](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures).
The agent does not request or display thought summaries.

## Commands

```text
coding-agent [--cwd PATH]
coding-agent run "TASK" [--cwd PATH] [--output rich|jsonl]
coding-agent resume SESSION_ID [--cwd PATH]
coding-agent sessions [--output table|json]
```

The interactive UI keeps normal terminal scrollback. Enter submits, Ctrl+J or Alt+Enter inserts a
newline, Ctrl+G opens `$VISUAL`/`$EDITOR`, Ctrl+L clears, Ctrl+C cancels input or an active model or
command operation, Esc cancels an active model/tool run, and Ctrl+D exits. Cancellation closes the
model stream, terminates the command process tree, and records a resumable cancelled turn. Completion
is available for slash commands, `$skills`, and `@workspace/files`.

The visible product name is **Forge Coding Agent**; `coding-agent` is the stable executable name.
The scrolling TUI uses a branded header, Markdown-rendered streaming responses, plan and approval
panels, and a prompt-toolkit status bar without entering the terminal's alternate screen.

Interactive management commands are:

| Command | Purpose |
| --- | --- |
| `/help [COMMAND]` | List commands with descriptions or show detailed usage for one command. |
| `/status` | Show the current session, model, permissions, context, plan, memory, and skills. |
| `/model ...` | Inspect models, switch the current model/provider, or reload `models.toml`. |
| `/steps [12-100|reset]` | Inspect or persist the tool-step budget for this workspace. |
| `/permissions [MODE]` | Inspect or change `prompt`, `auto`, or `read-only` approval policy. |
| `/plan` / `/diff` | Inspect the current plan or edits applied in this process. |
| `/memory ...` | List, enable, disable, remember, forget, or explicitly clear project memory. |
| `/skills ...` | List, search, enable, disable, or reload discovered skills. |
| `/compact` | Compact eligible older context without deleting the JSONL transcript. |
| `/resume [SESSION_ID]` / `/new` | Pick a recent workspace session or switch by ID; create a clean session. |
| `/raw [on|off]` | Inspect or set full tool-result rendering. |
| `/clear` / `/exit` | Clear terminal output, or save the session and exit. |

Run `/help COMMAND` inside the TUI for usage, scope, and side-effect details. Administrative
changes report whether they affect only the current session/process or persistent project data.

## Configuration

Non-secret settings use this precedence:

```text
CLI > environment > trusted coding-agent.toml > defaults
```

Copy [`coding-agent.toml.example`](coding-agent.toml.example) when project configuration is useful.
The defaults limit a turn to 24 tool steps, ten minutes, and 120 seconds per command. Valid tool-step
budgets are 12 through 100. `/steps N` stores an override under Forge's user data directory, keyed
by repository identity like project Memory, and never edits the workspace; `/steps reset` restores
the trusted project value or the default. Non-interactive execution returns code 3 when an approval
would be required; configuration failures return 2 and user cancellation returns 130.

## Safety model

- Every resolved path must remain beneath `--cwd`; traversal, absolute paths, and symlink/junction
  escapes are rejected.
- Edits require a unique old-text match and expected SHA-256. Overwrites also require the expected
  hash. Writes use a same-directory temporary file and atomic replacement.
- File changes show a unified diff with red/green line backgrounds before approval. The live status
  pauses to expose an explicit `1 once / 2 session / 3 deny` input prompt.
- Destructive commands such as `git reset --hard`, forced `git clean`, recursive removal, disk
  formatting, and shutdown are rejected rather than presented for approval.
- Child processes receive a secret-stripped environment, bounded output, a timeout, and process-tree
  termination.
- Repository `AGENTS.md`, configuration, and skills require hash-invalidated project trust.
- `AGENTS.md` matching is case-insensitive, nested repositories and transient/build directories are
  excluded, and nested rules are indexed by scope instead of being injected outside that scope.

See [`docs/architecture.md`](docs/architecture.md) and [`SECURITY.md`](SECURITY.md) for the detailed
boundaries.

## Sessions, memory, and skills

The complete JSONL transcript is retained in the user data directory. Context compaction preserves
the goal, constraints, completed work, failed approaches, test evidence, pending work, and the four
most recent complete user turns without deleting the original transcript or splitting a function-call
exchange. The context indicator estimates the complete model request, including system instructions
and tool schemas, rather than counting only visible chat text.

`/resume` without an ID shows the ten most recent sessions for the current workspace. Restoring a
session rebuilds its effective model context from the latest compaction snapshot plus subsequent
messages, while the TUI previews the last three user/assistant turns without replaying tool output.
Before a request is sent, interrupted histories are normalized in memory for strict compatible
providers; the durable JSONL transcript is not rewritten.

Project memory is off by default. `/memory remember TEXT` stores an explicitly approved fact for the
same repository only; secret-like values and large code blocks are rejected. At most eight relevant
records and 2,000 estimated tokens are injected.

Skills are discovered from `.agents/skills/NAME/SKILL.md` in the repository and the user's
`~/.agents/skills` directory. Only frontmatter metadata is read during discovery. Full instructions
and confined resources are loaded after explicit `$name` use or a local `activate_skill` call; skill
scripts never execute automatically.

## Development and verification

```text
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q --cov=coding_agent --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json
python scripts/check_coverage.py coverage.json
python evals/run_eval.py --dry-run
python -m build
```

On Windows, if `python -m build` fails while installing the isolated Hatchling environment and the
`build` frontend then raises `UnicodeDecodeError`, verify the package itself with already installed
build requirements:

```text
python -m pip install build "hatchling>=1.25"
python -m build --no-isolation
```

This workaround does not replace the clean isolated build in CI; it separates a local pip/output
decoding failure from a package metadata or backend failure.

CI runs Ruff, strict mypy, branch coverage, high-risk coverage gates, Bandit, dependency and secret
audits, wheel installation, and CLI smoke tests on Ubuntu and Windows with Python 3.11 and 3.12. It
does not receive an API key or call a real model.

The real-model harness contains five isolated tasks and repeats each three times. It measures task
pass rate, tool success, self-correction, tokens, latency, memory pollution, unexpected skill
activation, and dangerous-command leakage. See [`evals/README.md`](evals/README.md).

The two-minute recording outline is in [`docs/demo-script.md`](docs/demo-script.md). Current delivery
status and intentionally deferred work are tracked in [`docs/roadmap.md`](docs/roadmap.md). No
credentials, generated evaluation reports, session logs, or project memories should be committed or
recorded.
