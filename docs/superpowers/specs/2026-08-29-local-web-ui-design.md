# Forge Coding Agent Local Web UI Design

## Status

Approved on 2026-08-29. This document replaces the abandoned Qt Widgets desktop
exploration for the first graphical frontend. The existing CLI/TUI remains supported.

## Goal

Ship a polished, local-first graphical interface suitable for a two-minute product demo
without moving model, tool, approval, session, memory, skill, or workspace authority into
the browser.

The initial entry points are:

```powershell
pip install -e ".[web]"
coding-agent web --cwd .
python -m coding_agent web --cwd .
```

## Decision

P0 is a localhost Web UI built with React and TypeScript. A Python process serves bundled
static assets and a same-origin WebSocket on a random loopback port. P1 may wrap the same
renderer in Electron. Qt Widgets controls are not migrated.

Reusable semantics from the desktop exploration are limited to frontend-neutral runtime
construction, event presentation, approval brokering, history restoration, and safe file
preview. No QWidget layout or styling code is reused.

## Product principles

- The visible product name comes from `coding_agent.branding`.
- The graphical frontend is another first-party surface over the existing local Agent core.
- The browser is an untrusted renderer. It never receives credentials or arbitrary shell,
  tool, or filesystem capabilities.
- The UI shows user input, concise plans, observable actions, approvals, errors, validation,
  changes, and final output. It never exposes hidden chain-of-thought.
- Agent final output is always expanded. Routine read/search actions are grouped by default.
- Completion is evidence-based: validation results and changed files are separate from the
  model's prose. If no validation ran, the UI says so.
- The interface remains useful at 1024x700 and scales naturally to a 1920x1080 demo window.

## Architecture

```text
React renderer
  Session rail | Timeline | Context drawer | Composer
                       |
                       | same-origin WebSocket
                       v
Python UiGateway
  protocol validation | event sequence | turn coordinator | auth
                       |
                       v
RuntimeFactory -> AgentController
  SessionStore | MemoryStore | SkillRegistry | ApprovalPolicy
  ModelManager | ToolRegistry | WorkspacePaths
```

`RuntimeFactory` is independent of Rich, prompt-toolkit, FastAPI, and React. CLI/TUI and Web
construct controllers through the same factory, with their own event and approval callbacks.

The gateway owns one active `TurnCoordinator` per browser session. A turn runs on a worker
thread because `AgentController.run_turn()` is synchronous. The coordinator exposes start,
cancel, and approval resolution but never exposes direct tool execution.

## Versioned protocol

Every frame is JSON and includes `protocol_version: 1`. Requests include a client-generated
`request_id`; events include a monotonically increasing `seq`, `session_id`, and optional
`turn_id`.

Client requests:

- `initialize`
- `session.list`
- `session.create`
- `session.resume`
- `turn.start`
- `turn.cancel`
- `approval.resolve`
- `file.preview`
- `changes.list`
- `config.get`

Server events:

- `snapshot`
- `turn.started`
- `message.delta`
- `activity.upsert`
- `approval.requested`
- `approval.resolved`
- `plan.updated`
- `change.recorded`
- `context.updated`
- `turn.finished`
- `error`

Raw `AgentEvent` remains the controller contract. `AgentEventPresenter` converts raw events
into stable semantic view events, pairs tool call/result by call ID, and ignores historical
TEXT deltas when a final assistant message exists.

## Interface layout

### Session rail

The 240px rail shows the current project, new task, recent sessions, status, and changed-file
count. Search, archive, and settings are secondary actions. The current workspace is visible
in the center header as well.

### Timeline

The center column has a comfortable maximum reading width while action rows may use the full
available width. User tasks use a quiet tinted surface. Agent actions use compact rows and
subtle separators. Read/search/list actions aggregate into one activity group; write,
command, approval, error, validation, and final response remain distinct.

Markdown deltas are buffered for approximately 50ms. During streaming, incomplete Markdown
is repaired only for display. The final source text is re-rendered after completion.

### Context drawer

The 400-480px right drawer opens only for file preview, diff, approval detail, or validation
output. It is not a permanent dashboard. Closing it returns the width to the timeline.

### Composer

The composer is fixed to the bottom and grows between roughly 72 and 160px. Model, mode,
permissions, context usage, and send/stop are next to the input. Slash, skill, and file
completion use an anchored keyboard-accessible popover.

### Visual system

- Warm neutral backgrounds inspired by Apple and Google surface hierarchy.
- Blue is reserved for selection and primary actions; green for verified success; amber for
  pending approval; red for failure or destructive impact.
- Noto Sans SC is the primary UI font and JetBrains Mono is used for paths, model IDs, code,
  commands, and diffs. Fonts are bundled; the renderer loads no remote assets.
- Layout uses 4/8px spacing tokens, 10-14px radii, one-pixel separators, restrained shadows,
  and no grid of oversized cards.

## Approval interaction

Approval appears inline with action, subject, summary, cwd when applicable, and diff when
applicable. Available decisions are allow once, allow matching actions for this session, and
deny with optional feedback.

`ApprovalBroker` assigns an opaque approval ID, blocks only the worker thread, and resolves a
single pending request exactly once. Cancellation, disconnect, or server shutdown denies all
pending requests and signals turn cancellation. Session grants are cleared when session,
workspace, model, or permission mode changes.

## History and changes

SessionStore is the source of truth. Restoration uses durable final messages and structured
records and does not replay tool effects. Gemini thought signatures remain attached to
`extra_content.google.thought_signature` in model history and compaction.

P0 changed-file review is read-only. It shows file status, additions/deletions, and unified
diff in the context drawer. Undo, hunk acceptance, Git commit, push, and PR operations are not
claimed until a durable before/after change ledger exists and those operations traverse the
normal approval boundary.

## File preview

All preview paths are workspace-relative and resolved through `WorkspacePaths`. Absolute
paths, traversal, links escaping the workspace, binary content, and text larger than 2 MiB
are rejected. The browser cannot request arbitrary filesystem paths.

## Web security

- Bind only to `127.0.0.1` on an OS-assigned port.
- Serve static assets and WebSocket from one origin; do not enable wildcard CORS.
- Generate a random capability for each launch, exchange it once for an HttpOnly,
  SameSite=Strict cookie, and remove it from the visible location.
- Validate Host, Origin, request types, IDs, lengths, and state transitions.
- Apply a strict CSP and load no remote scripts, fonts, images, frames, or workers.
- Confirm external navigation. Disable remote Markdown images and raw HTML.
- Never serialize API keys, authorization headers, secret environment values, or unfiltered
  exception locals.
- Allow one controlling browser client; reject or downgrade additional clients.
- Rotate credentials and deny pending approvals on shutdown.

## Technology

- Python 3.11/3.12, FastAPI/Starlette, Uvicorn, Pydantic.
- React, TypeScript, Vite, Zustand, Radix Primitives.
- react-markdown, remark-gfm, rehype-sanitize, Shiki with a language allowlist.
- react-diff-view for P0 read-only diff.
- Vitest, Testing Library, pytest, and Playwright.

FastAPI and Uvicorn are optional `web` dependencies and are imported only by the `web`
command. React source is not installed as a runtime dependency; its compiled assets are
bundled in the Python wheel.

## P0 acceptance

1. CLI/TUI import and run without Web dependencies installed.
2. `coding-agent web --cwd .` starts on loopback, opens the app, and reports installation
   instructions with exit code 2 if Web dependencies or built assets are absent.
3. A real turn streams text and compact activities, supports cancellation, and finishes with
   stable status.
4. Approval allow-once, allow-session, deny, disconnect, and shutdown paths are tested.
5. Sessions list, create, resume, and restore without duplicate streamed text.
6. Changed files open in a safe read-only diff drawer.
7. No UI, session, log, or test artifact contains API keys.
8. The app passes offscreen browser tests at 1024x700 and a 1920x1080 demo viewport.

## Explicitly deferred

Multi-agent execution, worktrees as a product feature, code editing, terminal emulation,
browser automation, MCP management, LAN access, mobile access, Git commit/push/PR, installer
packaging, and hidden reasoning display are outside P0.

