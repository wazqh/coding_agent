# Architecture

Forge separates terminal interaction, orchestration, model transport, local tools, safety policy,
context, persistence, project memory, and skills. All user-visible front ends consume the same
`AgentEvent` stream, so Rich, JSONL, tests, and evaluations observe the same behavior.

```text
CLI / prompt_toolkit / Rich
             |
      AgentController
       /     |      \
ModelClient  ToolRegistry  ContextManager
                |          /      |       \
          Safety policy  Session  Memory  Skills
```

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
failed approaches, test evidence, pending work, and four recent interaction groups. The transcript
on disk is append-only and remains available for replay.

## Trust and execution boundary

Repository configuration, instructions, and skills are hashed. Trust is invalidated when those
resources change. Paths are resolved after normalization and must remain inside the workspace.
Mutations are hash-guarded and atomic. Command screening precedes approval; directly destructive
commands are never executable. Skills can describe scripts, but loading a skill never executes one.

The model API receives messages and function schemas only. Tool execution, argument validation,
approval, filesystem access, process management, looping, persistence, and termination stay local.
