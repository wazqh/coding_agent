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

## Commands

```text
coding-agent [--cwd PATH]
coding-agent run "TASK" [--cwd PATH] [--output rich|jsonl]
coding-agent resume SESSION_ID [--cwd PATH]
coding-agent sessions [--output table|json]
```

The interactive UI keeps normal terminal scrollback. Enter submits, Ctrl+J or Alt+Enter inserts a
newline, Ctrl+G opens `$VISUAL`/`$EDITOR`, Ctrl+L clears, Ctrl+C cancels input, and Ctrl+D exits.
Completion is available for slash commands, `$skills`, and `@workspace/files`.

Supported commands are `/help`, `/status`, `/model`, `/permissions`, `/plan`, `/diff`, `/memory`,
`/skills`, `/compact`, `/resume`, `/new`, `/clear`, `/raw`, and `/exit`.

## Configuration

Non-secret settings use this precedence:

```text
CLI > environment > trusted coding-agent.toml > defaults
```

Copy [`coding-agent.toml.example`](coding-agent.toml.example) when project configuration is useful.
The defaults limit a turn to 24 tool steps, ten minutes, and 120 seconds per command. Non-interactive
execution returns code 3 when an approval would be required; configuration failures return 2 and
user cancellation returns 130.

## Safety model

- Every resolved path must remain beneath `--cwd`; traversal, absolute paths, and symlink/junction
  escapes are rejected.
- Edits require a unique old-text match and expected SHA-256. Overwrites also require the expected
  hash. Writes use a same-directory temporary file and atomic replacement.
- File changes show a unified diff before approval. Approval can be once, session-wide, or denied.
- Destructive commands such as `git reset --hard`, forced `git clean`, recursive removal, disk
  formatting, and shutdown are rejected rather than presented for approval.
- Child processes receive a secret-stripped environment, bounded output, a timeout, and process-tree
  termination.
- Repository `AGENTS.md`, configuration, and skills require hash-invalidated project trust.

See [`docs/architecture.md`](docs/architecture.md) and [`SECURITY.md`](SECURITY.md) for the detailed
boundaries.

## Sessions, memory, and skills

The complete JSONL transcript is retained in the user data directory. Context compaction preserves
the goal, constraints, completed work, failed approaches, test evidence, pending work, and the four
most recent interaction groups without deleting the original transcript.

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

CI runs Ruff, strict mypy, branch coverage, high-risk coverage gates, Bandit, dependency and secret
audits, wheel installation, and CLI smoke tests on Ubuntu and Windows with Python 3.11 and 3.12. It
does not receive an API key or call a real model.

The real-model harness contains five isolated tasks and repeats each three times. It measures task
pass rate, tool success, self-correction, tokens, latency, memory pollution, unexpected skill
activation, and dangerous-command leakage. See [`evals/README.md`](evals/README.md).

The two-minute recording outline is in [`docs/demo-script.md`](docs/demo-script.md). No credentials,
generated evaluation reports, session logs, or project memories should be committed or recorded.
