# Architecture

Forge separates terminal and browser interaction, orchestration, model transport, local tools,
safety policy, context, persistence, project memory, and skills. All user-visible front ends consume
the same `AgentEvent` stream, so TUI, Web, Rich, JSONL, tests, and evaluations observe the same
behavior.

```text
CLI / prompt_toolkit / Rich       React Web renderer
             |                           |
             |                 typed loopback gateway
             |                    semantic presenter
             |                           |
             +------ RuntimeFactory -----+
                         |
                  AgentController
                   /     |      \
            ModelClient  ToolRegistry  ContextManager
                            |          /      |       \
                      Safety policy  Session  Memory  Skills
```

## Local Web boundary

`coding-agent web` lazily imports FastAPI/Uvicorn, binds only to `127.0.0.1` on an OS-assigned port,
and serves bundled versioned React assets. A single-use fragment capability is exchanged for an
HttpOnly SameSite=Strict cookie after exact Host and Origin validation. One authenticated WebSocket
becomes the controlling client; disconnecting cancels active work and denies pending approvals.

The browser receives a closed, versioned semantic protocol: snapshots, final/streamed messages,
grouped activity, plans, approval requests/results, context usage, bounded file previews, recorded
diffs, completion, and recoverable errors. It cannot invoke arbitrary tools, read absolute paths, or
submit shell commands outside an approval request created by the controller. File preview resolves
through `WorkspacePaths`, rejects traversal and workspace escapes, and is limited to valid UTF-8
text no larger than 2 MiB. Historical restore uses final user/assistant messages while ignoring
historical text deltas, so answers are not duplicated.

The React layer is transport-independent: Zustand projects semantic events into a compact timeline,
while the WebSocket transport validates every inbound frame before mutation. Noto Sans SC and
JetBrains Mono are bundled locally; Markdown disables raw HTML and remote resource loading. The
responsive layout uses a session rail, fluid conversation column, contextual inspector, and fixed
composer, with overlay behavior at narrow widths.

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

- Working state exists only in the current process and contains the goal, plan, recent calls, diffs,
  approvals, and active skills.
- Session JSONL stores messages, tool observations, events, usage, compaction points, and termination.
- Approved project memory is stored separately, is disabled by default, filtered for secrets, and
  keyed by normalized repository root plus Git remote.
- `AGENTS.md` is repository-owned policy. Skills are reusable procedures. Neither is memory.

At 70% of the context window, deterministic compaction preserves the goal, constraints, changes,
failed approaches, test evidence, pending work, and four recent complete user turns. A compacted
snapshot has one effective summary and never starts inside an assistant/tool function-call group.
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
