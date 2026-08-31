# Architecture

Forge separates desktop and terminal interaction, orchestration, model transport, local tools,
safety policy, context, persistence, project memory, and skills. All user-visible front ends consume
the same `AgentEvent` stream, so Electron, TUI, Rich, JSONL, tests, and evaluations observe the same
behavior.

```text
CLI / prompt_toolkit / Rich              Electron
             |                         main process
             |                              |
             |                    sandboxed preload IPC
             |                              |
             |                       React renderer
             |                              |
             |                    typed loopback gateway
             |                     semantic presenter
             |                              |
             +--------- RuntimeFactory -----+
                              |
                       AgentController
                        /     |      \
                 ModelClient  ToolRegistry  ContextManager
                                 |          /      |       \
                           Safety policy  Session  Memory  Skills
```

## Desktop process boundary

Electron main selects the workspace, supervises the Python gateway, owns native dialogs and window
policy, and stores provider credentials through the shared Python operating-system credential
service. Existing Electron `safeStorage` entries are migrated once and retained only as a
process-local fallback when secure system storage is unavailable. The renderer never receives a
read-secret API. Environment variables remain explicit process-local overrides. The renderer has
`nodeIntegration` disabled, context isolation and sandboxing enabled,
and can access only the narrow preload API. Navigation is restricted to the private gateway;
external HTTP(S) links require confirmation before opening in the system browser.

The gateway binds only to `127.0.0.1` on an OS-assigned port and serves bundled versioned React
assets. A single-use fragment capability is exchanged for an HttpOnly SameSite=Strict cookie after
exact Host and Origin validation. One authenticated WebSocket becomes the controlling client;
disconnecting cancels active work and denies pending approvals. The loopback transport is an
internal desktop boundary, not a remote service or a transfer of filesystem authority to Electron.

The browser receives a closed, versioned semantic protocol: snapshots, final/streamed messages,
grouped activity, plans, approval requests/results, context usage, bounded file previews, durable
change review, exact change Undo, session/project-list management, completion, and recoverable
errors. It cannot invoke
arbitrary tools, read absolute paths, or submit shell commands outside an approval request created
by the controller. File preview resolves through `WorkspacePaths`, rejects traversal and workspace
escapes, and is limited to valid UTF-8 text no larger than 2 MiB. Historical restore uses final
user/assistant messages while ignoring historical text deltas, so answers are not duplicated.
Initialization restores the most recent meaningful session for the active workspace, falling back
to its latest blank session; it creates a Session only when the workspace has none.

Electron treats gateway replacement as an expected lifecycle during model or workspace switching.
The renderer enters a labeled transition state before the old socket closes, while the transport
retries a short bounded startup handshake. Only an exhausted or unexpected disconnect becomes the
recoverable “cannot connect” state, so a deliberate restart is not presented as a failure.

The Resources inspector derives a contextual file tree from paths already present in durable changes
and structured activity. It does not enumerate the entire repository or introduce a second filesystem
boundary. Directories are collapsible, changed files carry created/modified status, and selecting a
leaf requests the same bounded preview protocol used by change review. The preview remains read-only
and renders locally with file metadata and line numbers.

The React layer is transport-independent: Zustand projects semantic events into a project/session
tree, readable activity timeline, plan, approvals, final output, and task inspector, while the
WebSocket transport validates every inbound frame before mutation. Noto Sans SC and JetBrains Mono
are bundled locally; Markdown disables raw HTML and remote resource loading. The responsive layout
uses a collapsible session rail, fluid conversation column, contextual inspector, and anchored
composer, with overlay behavior at narrow widths. Routine tool payloads are converted to labeled
fields and concise summaries rather than exposed as raw JSON. Approval, execution, and result
events share the model tool-call ID, allowing the renderer to update one operation card throughout
its lifecycle. Successful routine reads may be grouped as an exploration phase; mutations,
validation, approvals, failures, and hard-safety blocks remain individually inspectable.

Review and preview surfaces are siblings of the conversation rather than nested code editors. A
selected resource or change opens an adjacent workspace-confined pane that never covers the project
rail. Its header and controls remain content-sized and non-scrolling; only the file or Diff body owns
the remaining height and scroll position. Unified and side-by-side Diff, command details, and file
previews share JetBrains Mono metrics, stable line-number gutters, readable line spacing, and thin
scrollbars. Secondary copy remains lower-emphasis without becoming unreadable or carrying state by
itself.

Interaction hierarchy is semantic as well as visual: active inspector tabs use text weight and an
indicator, nested resource groups expose tree roles and guide lines, Slash commands render as one
row per command, and every save, restart, accept, undo, delete, or connection action produces a
visible state change. Transient success receipts are emitted only by a new state transition; loading
persisted review state or reopening the inspector does not replay them. Animations have
reduced-motion fallbacks and never replace text/status output.

Read-only code navigation is part of the local `ToolRegistry`: `list_symbols`, `find_definition`,
and `find_references` share an in-process, modification-time-invalidated index. Python uses the
standard-library AST for definitions and references; common compiled and web languages use a
bounded lexical adapter. The index is ephemeral, never leaves the workspace, and appears in the
desktop timeline as grouped workspace exploration rather than raw tool data.

## Turn lifecycle

The controller moves through `IDLE -> THINKING -> TOOL_PENDING -> EXECUTING -> OBSERVING` and loops
until `COMPLETED`, `FAILED`, or `CANCELLED`. Plans are visible tool-managed state, not hidden model
reasoning. Tool calls execute in model order, and every result returns the fixed fields `ok`, `code`,
`summary`, `data`, `retryable`, and `truncated`.

A valid assistant message without tool calls completes the turn. Identical failed calls warn after
two attempts and stop after the third. A turn is bounded by 24 tool steps and ten minutes by default.
Connection, timeout, rate-limit, and server failures receive bounded exponential retry in the model
adapter; authentication and request errors do not. Cancellation closes an active model stream and
terminates the complete command process tree before the cancelled turn is persisted.

## Persistence controls

- Working state contains the goal, plan, recent calls, approvals, and active skills. Each tool call
  carries one stable operation ID through approval, execution, and observation.
- Session JSONL stores messages, tool observations, semantic events, usage, compaction points,
  termination, and an append-only change ledger. Each bounded change record includes its kind,
  workspace-relative path, before/after hashes, rendered Diff, reversible backup when available,
  and review state. Restore reconstructs review state without replaying side effects.
- Approved project memory is stored separately, is disabled by default, filtered for secrets, and
  keyed by normalized repository root plus Git remote.
- `AGENTS.md` is repository-owned policy. Skills are reusable procedures. Neither is memory.

Desktop accept marks a change reviewed without touching the workspace. Undo applies the
selected recorded change in reverse only when the current file still
matches the recorded after-state. Later edits cause a recoverable conflict instead of an unsafe
overwrite; bulk undo runs in reverse order and reports partial conflicts. Deleting a Session
removes only Memory records whose evidence identifies that Session; failure in either store rolls
the operation back. Removing a project from the recent-project index preserves its directory, Git
data, sessions, and Memory so reopening it is recoverable.

Project-scoped verification hooks are disabled by default and hold at most eight validated command
strings. After a turn creates a change, the controller runs them through the existing command tool,
approval policy, hard-safety screening, cancellation, timeout, and Step budget. A failure becomes a
normal tool observation and permits at most two model repair attempts. Validation events are shown
as deterministic receipts and are never inferred from final assistant text.

At 70% of the complete request size (messages plus tool schemas), deterministic compaction runs
before a new user turn rather than inside an active tool chain. It preserves the goal, constraints,
visible prior-turn decisions, changes, failed approaches, test evidence, pending work, and up to
four recent complete user turns. A compacted snapshot has one effective summary and never starts
inside an assistant/tool function-call group.
The threshold estimates the complete request, including tool schemas. Before transport, adjacent
system or interrupted user records and legacy invalid snapshot boundaries are normalized in memory
for strict compatible providers; the append-only transcript is not rewritten and remains available
for replay.

## Trust and execution boundary

Repository configuration, instructions, and skills are hashed. Trust is invalidated when those
resources change. Paths are resolved after normalization and must remain inside the workspace.
Mutations are hash-guarded and atomic. Command screening precedes approval; directly destructive
commands are never executable. Skills can describe scripts, but loading a skill never executes one.

The model API receives messages and function schemas only. Tool execution, argument validation,
approval, filesystem access, process management, looping, persistence, and termination stay local.
