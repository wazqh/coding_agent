# Forge Coding Agent

Forge is an original Python 3.11/3.12 local coding agent. It combines an Electron desktop workspace and
a scrolling professional terminal UI with a locally controlled model-tool-observation loop,
resumable sessions, approved project memory, lazy `SKILL.md` workflows, and strict workspace safety.
It does not use an agent framework, hosted code execution, or a remote file service.

## Install and start

Create a virtual environment and install the package. Provider credentials can be saved from the
desktop model manager or the TUI's guided `/model add PROVIDER` flow; environment variables remain
available as explicit process-local overrides:

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

### Electron desktop

The desktop client is currently delivered from source and uses Node.js 22 for the documented
development path. Install the Python gateway and JavaScript dependencies once, then launch Electron
with the workspace Forge may control:

```powershell
python -m pip install -e ".[desktop]"
Set-Location web
npm ci
$env:FORGE_WORKSPACE = (Resolve-Path ..).Path
npm run desktop:dev
```

Set `FORGE_WORKSPACE` to another absolute path to open a different project. For a direct Electron
launch, `& .\node_modules\.bin\electron.cmd . --cwd "D:\path\to\project"` remains supported and
takes precedence over `FORGE_WORKSPACE`. `FORGE_PYTHON` may select the Python executable used for
the local runtime. The desktop provides project-organized sessions, a visible
Agent activity timeline and plan, inline three-way approvals, Markdown output, `/`/`@`/`$`
completion, model/provider onboarding, runtime controls, and a resizable task inspector. Daily
model switching is a flat model-first list; the lower-frequency connection manager separately
handles provider metadata, credentials, and each provider's expandable model catalog. The
inspector separates **Settings** (model, permissions, and Step budget) from **Run**. Run itself has
two focused views: **Command history** for real command output and **Verification** for project
checks, the automatic-verification switch, Agent TDD guidance, and deterministic evidence. Slash
commands open the corresponding panel directly. When no checks are configured, Forge derives
one-click suggestions from project markers such as `pyproject.toml`, `package.json`, `Cargo.toml`,
and `go.mod`; discovery only reads workspace-confined metadata and never executes a command. Its
**Resources** tab groups files read or changed
in the current session into a collapsible tree; selecting a file opens an adjacent
workspace-confined, read-only preview with metadata, line numbers, and syntax highlighting for
common source formats. Diff rendering keeps review semantics ahead of syntax coloring. The
Skills view can turn a natural-language requirement into an editable draft, fall back to a local
template when the model is unavailable, and writes only after the user chooses personal or
trusted-project scope and confirms creation. Approval,
execution, and result states share one operation card instead of producing duplicate receipts.
The inspector keeps an append-only, restart-safe change ledger with unified/side-by-side/fullscreen
Diff review, **accept** or conflict-safe **undo** for one or all changes. It resumes the most recent
meaningful session for the selected workspace on launch instead of creating an empty conversation;
**New conversation** is the explicit
way to start a clean session. Sessions can be deleted in place, together with only the Memory facts
that carry evidence from that session. A project can be removed from Forge's recent list after
confirming its exact path; this never deletes workspace files, Git data, sessions, or Memory. The
desktop uses the same `AgentController`, session store,
local tools, approval policy, workspace confinement, Memory, and Skills as the TUI.

Electron supervises a private loopback Python gateway; it does not run the CLI as a child or move
model/tool authority into JavaScript. A one-time capability is exchanged for an HttpOnly,
SameSite=Strict cookie, Host and Origin are restricted to the exact loopback listener, and only one
controlling WebSocket is accepted. Provider keys use the desktop credential bridge and never enter
renderer state, WebSocket frames, sessions, Memory, or `models.toml`. Remote Markdown resources are
not loaded. Tool details are presented as labeled, human-readable fields; the normal interface does
not expose raw JSON payloads.

Do not append `-- --cwd ...` to `npm run desktop:dev`: npm interprets that form as a workspace
selector in some versions. Use `FORGE_WORKSPACE`, or invoke the local Electron binary directly as
shown above. During startup and deliberate model/workspace restarts, the renderer shows one
transition state and retries the short gateway handshake before presenting a recoverable connection
error.

### Multiple OpenAI-compatible providers

Create `models.toml` in the Forge user data directory (the directory selected by
`CODING_AGENT_DATA_DIR`, or the platform default) to reuse provider profiles across projects. The
file stores only non-secret provider metadata, an optional environment override name, and a
credential reference. Secret values are stored by the operating system (Windows Credential
Manager, macOS Keychain, or Linux Secret Service), never in the catalog or active-selection state.

```toml
default_provider = "gemini"

[providers.gemini]
base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key_env = "GEMINI_API_KEY"
credential_ref = "provider:gemini"
default_model = "gemini-3.7-flash"
models = ["gemini-3.7-flash", "gemini-3.1-pro"]
compatibility = "gemini"

[providers.deepseek]
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"
credential_ref = "provider:deepseek"
default_model = "deepseek-chat"
models = ["deepseek-chat", "deepseek-reasoner"]
```

Use `/model add PROVIDER` for guided Base URL, Model ID, and masked API Key setup. Use
`/model use PROVIDER [MODEL_ID]` to change provider, `/model MODEL_ID` to change the model within
the current provider, and `/model reload` after editing the catalog. The active
provider and model are restored on the next launch. `--model` temporarily overrides the restored
model while retaining the selected provider. A non-empty `api_key_env` value always overrides the
stored credential for that process. Without `models.toml`, the existing `OPENAI_API_KEY`,
`OPENAI_BASE_URL`, and `CODING_AGENT_MODEL` flow remains unchanged.

The desktop connection manager includes presets for OpenAI, Kimi, DeepSeek, Qwen/DashScope, GLM,
Hunyuan, Gemini, OpenRouter, and regional Alibaba, Huawei, and Tencent MaaS gateways. Enter the
**API root**, not a complete resource endpoint: Forge calls the OpenAI SDK's Chat Completions API
and appends `/chat/completions` itself. For example, use
`https://open.bigmodel.cn/api/paas/v4`, not a URL ending in `/chat/completions`. The form previews
the final request URL and offers a one-click correction for common copied endpoints; the Python
writer enforces the same rule for TUI and imported configurations. Saved providers can be edited,
duplicated, or deleted, and a blank API Key while editing preserves the existing system credential.
After switching, the desktop restarts the local runtime and performs a minimal connectivity probe
that reports authentication, model, rate-limit, or network failures without exposing provider
responses or secret values.

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
| `/model ...` | Add providers securely, inspect models, switch model/provider, or reload metadata. |
| `/steps [12-100|reset]` | Inspect or persist the tool-step budget for this workspace. |
| `/permissions [MODE]` | Inspect or change `prompt`, `auto`, or `read-only` approval policy. |
| `/plan` / `/diff` | Inspect the current plan or edits applied in this process. |
| `/memory ...` | List, enable, disable, remember, forget, or explicitly clear project memory. |
| `/skills ...` | List, search, enable, disable, or reload discovered skills. |
| `/compact` | Compact eligible older context without deleting the JSONL transcript. |
| `/resume [SESSION_ID]` / `/new` | Pick a recent workspace session or switch by ID; create a clean session. |
| `/raw [on|off]` | Inspect or set complete, labeled tool details (never a raw JSON dump). |
| `/clear` / `/exit` | Clear terminal output, or save the session and exit. |

The local tool registry also exposes `list_symbols`, `find_definition`, and `find_references`.
Python files use the standard-library AST; TypeScript/JavaScript, C/C++, Rust, Go, Java, and C# use
a bounded lightweight lexical index. Parsed files are cached by modification time for the running
process, all paths remain workspace-confined, and the GUI groups these read-only navigation calls
with ordinary workspace exploration instead of exposing protocol payloads.

Desktop presentation follows the same evidence-first rule as the TUI: plans are explicit tool
state, routine read/search activity may be grouped without hiding mutations or failures, approval
and execution update one operation card, and final model text remains distinct from deterministic
validation receipts. The interface uses locally bundled fonts, readable secondary-text contrast,
thin code scrollbars, directory guide lines, keyboard completion, and reduced-motion fallbacks;
motion never carries status by itself.

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

The desktop **Task inspector → Run → Verification** view can store up to eight project-scoped
verification commands, one command per line. Project-derived suggestion chips reduce setup guesswork,
but a command becomes active only after the user explicitly saves it. Automatic verification is an explicit switch. With it
off, a completed turn remains visibly **unverified** and can be checked on demand from its timeline
footer. With it on, a file-changing turn runs the configured checks through the normal command
safety, approval, cancellation, timeout, and Step-budget boundaries before its final answer is
released. Optional **Agent TDD** guidance asks the Agent to write focused tests and execute them with
ordinary tools; the deterministic verification layer—not the model—owns the automatic trigger. A
failing observation is returned to the model for at most two repair attempts. The final failed
receipt offers a visible repair action that sends the command and failure evidence back as a new
user-visible task. Hard safety blocks cannot be overridden by verification settings or GUI controls.

## Safety model

- Every resolved path must remain beneath `--cwd`; traversal, absolute paths, and symlink/junction
  escapes are rejected.
- Edits require a unique old-text match and expected SHA-256. Overwrites also require the expected
  hash. Writes use a same-directory temporary file and atomic replacement.
- File changes show a unified diff with red/green line backgrounds before approval. The live status
  pauses to expose an explicit `1 once / 2 session / 3 deny` input prompt.
- Destructive commands such as `git reset --hard`, forced `git clean`, recursive removal, disk
  formatting, and shutdown are rejected before execution rather than presented for approval. The
  desktop identifies these as non-overridable hard-safety decisions and shows the attempted command
  plus a safer next step without exposing raw protocol JSON.
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

On desktop startup, Forge selects the most recently updated session for the current workspace that
contains a user task. If the workspace contains only blank sessions, it reuses the newest blank
session; a new Session is created only when none exists or the user explicitly requests one.
Historical final messages and structured events are restored without replaying side effects or
historical text deltas.

Project memory is off by default. `/memory remember TEXT` stores an explicitly approved fact for the
same repository only; secret-like values and large code blocks are rejected. At most eight relevant
records and 2,000 estimated tokens are injected.

Skills are discovered from `.agents/skills/NAME/SKILL.md` in the repository and the user's
`~/.agents/skills` directory. Only frontmatter metadata is read during discovery. Full instructions
and confined resources are loaded after explicit `$name` use or a local `activate_skill` call; skill
scripts never execute automatically. Desktop-created Skills are always reviewable before writing;
project Skills require an already trusted workspace and existing names are never overwritten.

## Development and verification

```text
python -m pip install -e ".[dev,desktop]"
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q --cov=coding_agent --cov-branch \
  --cov-report=term-missing --cov-report=json:coverage.json
python scripts/check_coverage.py coverage.json
python evals/run_eval.py --dry-run
python -m build

cd web
npm ci
npm test
npm run build
npm run desktop:build
npx playwright install chromium
npm run test:e2e
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

CI runs Ruff, strict mypy, branch coverage, and high-risk coverage gates on Ubuntu and Windows with
Python 3.11 and 3.12. Security audits plus wheel installation and CLI smoke tests run on Ubuntu with
Python 3.12. Desktop CI type-checks and builds Electron main/preload and the React renderer, checks
that committed production assets match their source, and executes Vitest plus the renderer demo path
at 1024×700 and 1920×1080 on Windows and Linux. It does not receive an API key or call a real model.

The real-model harness contains five isolated tasks and repeats each three times. It measures task
pass rate, tool success, self-correction, tokens, latency, memory pollution, unexpected skill
activation, and dangerous-command leakage. See [`evals/README.md`](evals/README.md).

The two-minute recording outline is in [`docs/demo-script.md`](docs/demo-script.md). Current delivery
status and intentionally deferred work are tracked in [`docs/roadmap.md`](docs/roadmap.md). No
credentials, generated evaluation reports, session logs, or project memories should be committed or
recorded.

## Assessment delivery

The assessment deadline is **2026-09-02 24:00 China Standard Time**. The submitted archive contains
`README.txt` and one MP4 video only; `README.txt` is capped at 1000 Chinese characters and includes
the public repository address, launch instructions, and feature summary. The video is capped at two
minutes and 200 MB. The public repository must retain its pushed history and must not receive new
commits after the deadline.

These are delivery constraints from the supplied assessment brief, not automated guarantees.
Clean-clone acceptance, the real-model evaluation, final video review, CI, and the exact demonstrated
commit must all be checked again before submission.
