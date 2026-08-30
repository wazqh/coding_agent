# Forge Coding Agent Electron Desktop V2 Design

## Status

Implemented and integrated on 2026-08-30. Electron is now the primary graphical frontend and the
TUI remains supported. References below to a comparison branch, separate worktree, or Web V1 record
the implementation phase and are not current launch instructions; use the repository README.

## Goal

Deliver a polished Electron + React desktop interface for Forge Coding Agent that reuses the
existing Python `AgentController`, local tools, approvals, sessions, Memory, Skills, model catalog,
workspace settings, and safety boundaries. Every user-facing capability currently available in the
interactive TUI must have an equivalent desktop interaction before V2 is considered complete.

The comparison build is a development delivery, not an installer:

```powershell
npm ci
npm run desktop:dev -- --cwd .
```

Installer packaging, automatic updates, code signing, and EXE/MSIX/DMG/AppImage production are
deferred until the interaction design is accepted.

## Product decisions

- Electron is a trusted desktop shell, not a second Agent implementation.
- Electron main starts and supervises the existing Python local gateway. The gateway constructs
  the runtime through `RuntimeFactory` and remains the only authority for model calls, tools,
  approvals, persistence, and workspace access.
- React renderer is untrusted. It receives semantic view data and sends a closed set of typed
  requests. It never receives credentials, unrestricted filesystem access, a shell, or arbitrary
  environment values.
- The V1 Web branch remains unchanged and launchable. V2 lives on `feat/electron-ui-v2` so both
  versions can be compared with identical Agent behavior.
- Multi-agent, embedded editor, terminal emulator, Git push/PR, automatic undo, and hidden
  chain-of-thought are not introduced.

## Architecture

```text
Electron main
  window lifecycle | Python process supervisor | safe workspace picker
  external-link confirmation | typed preload bridge
                              |
                              | launches loopback gateway and consumes one-time handshake
                              v
Python UI gateway
  protocol validation | semantic events | turn coordinator | approval broker
                              |
                              v
RuntimeFactory -> AgentController
  ModelManager | SessionStore | MemoryStore | SkillRegistry
  ApprovalPolicy | ToolRegistry | WorkspacePaths | WorkspaceSettings

Electron renderer (React)
  project/session rail | task narrative | activity audit | diff inspector
  management center | composer and completion
```

The Python gateway remains bound to `127.0.0.1` on an OS-assigned port. Electron main consumes a
machine-readable startup handshake without printing its capability and loads the one-time URL into
the window. The existing HttpOnly cookie exchange removes the capability from the visible URL.
Only one controlling renderer is accepted.

The Electron window uses `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, a
strict CSP, disabled arbitrary navigation, and denied permission requests. Preload exposes only:

- application and gateway readiness,
- choose/open workspace through a native directory dialog,
- confirmed external-link opening,
- window minimize/maximize/close actions,
- application shutdown notification.

It does not expose generic IPC, `fs`, child processes, environment variables, or secrets.

## Desktop lifecycle

Electron main owns explicit states:

```text
starting -> ready -> stopping -> stopped
    |         |
    +-------> failed
```

The visible conversation owns explicit states:

```text
idle -> requesting -> awaiting_approval -> executing_tool
  ^          |                |                  |
  |          +----------------+------------------+
  |                                             |
  +--- completed | cancelled | failed <----------+
```

Closing the window cancels the active turn, denies pending approvals, waits briefly for the Python
gateway, and then terminates only the child process created by this Electron instance. Switching
workspace is disabled while a turn or approval is active. When idle, switching workspace restarts
the gateway with a new capability and clears renderer state before loading the new workspace.

## TUI capability parity

Desktop actions are semantic requests, not terminal strings forwarded into `InteractiveShell`.
Slash commands remain available in the composer as keyboard shortcuts to the same actions.

| TUI capability | Desktop equivalent |
| --- | --- |
| Send multiline task | Growing composer; Enter sends and Shift+Enter inserts a newline |
| Esc cancellation | Esc and visible Stop action cancel the active turn or pending approval |
| `/help [COMMAND]` | Searchable command palette with usage, details, and side effects |
| `/status` | Runtime inspector with session, model, provider, permissions, resources, context, and budgets |
| `/model` and `/model use PROVIDER [MODEL_ID]` | Model picker with provider/model grouping and current selection |
| `/model MODEL_ID` | Change model ID within the active provider for the next turn |
| `/model reload` | Reload model catalog and report configuration diagnostics without revealing keys |
| `/steps`, `/steps 12-100`, `/steps reset` | Project-bound maximum-step control; minimum 12; changes apply next turn |
| `/permissions prompt\|auto\|read-only` | Permission selector; changing it revokes session grants |
| `/plan` | Plan panel with pending/in-progress/completed steps and empty state |
| `/diff` | Cumulative changed-file summary and read-only unified diff inspector |
| `/memory list` | Project Memory panel with injection state and confirmed facts |
| `/memory on\|off` | Current-process Memory injection switch |
| `/memory remember TEXT` | Add a confirmed project fact |
| `/memory forget ID` | Delete one fact with confirmation |
| `/memory clear confirm` | Destructive confirmation before clearing project facts |
| `/skills [list]` | Searchable Skills panel with source, conflict, enabled, and active states |
| `/skills search QUERY` | Skill filtering and command-palette search |
| `/skills enable\|disable NAME` | Session-scoped skill enable/disable action |
| `/skills reload` | Reload trusted resources while preserving session disable choices |
| `/compact` | Context action showing estimated tokens before and after compaction |
| `/resume [SESSION_ID]` | Recent session list, search, resume, and copy Session ID |
| `/new` | New conversation action that resets plan, approvals, and activated skills |
| `/clear` | Clear only the current rendered timeline after confirmation; persisted history remains |
| `/raw on\|off` | Toggle structured raw tool results in expandable activity details |
| `/exit` and Ctrl+D | Desktop close flow with session handoff information |
| `$skill` completion | Anchored, keyboard-accessible skill completion |
| `@file` completion | Workspace-confined file completion with bounded results |
| Slash completion | Full-width command palette with argument-aware provider/model/steps completion |
| Tool streaming and audit | Compact activity groups plus expandable name, arguments, approval, result, duration, and error |
| Inline approval | Allow once, allow matching actions for session, or deny |
| Session restoration | Durable final messages and structured events; historical side effects never replay |

TUI-only presentation mechanics such as terminal `NO_COLOR`, external terminal editor invocation,
and ordinary terminal scrollback do not map literally. Their product outcomes map to accessible
desktop colors, the multiline composer, durable session history, copy actions, and native scrolling.

## Versioned desktop protocol

V2 extends the closed request/event union and increments its protocol version. Every renderer
request contains a bounded `request_id`; every event contains a monotonic `seq`, `session_id`, and
optional `turn_id`.

New semantic requests include:

- `runtime.status`
- `model.list`, `model.select`, `model.reload`
- `steps.get`, `steps.set`, `steps.reset`
- `permissions.get`, `permissions.set`
- `plan.get`
- `memory.list`, `memory.toggle`, `memory.remember`, `memory.forget`, `memory.clear`
- `skills.list`, `skills.toggle`, `skills.reload`
- `context.get`, `context.compact`
- `display.raw.set`, `display.clear`
- `completion.query`

The gateway validates every request, rejects management mutations while busy, and uses dedicated
application services instead of calling private `InteractiveShell` methods. Shared management
services are frontend-neutral so the TUI and Electron cannot drift in validation or persistence.

Semantic events add stable lifecycle, command result, model catalog, workspace setting, memory,
skills, compaction, completion, and resource status payloads. Errors state the failed stage,
whether a side effect may have occurred, and the recovery action. Secret filtering occurs before
serialization.

## Interface

### Three-column task cockpit

The wide layout follows the supplied HammerCode prototype without copying its branding or exact
controls:

- A 248px left rail shows the current workspace, a strong New conversation action, searchable
  recent sessions, and a quiet settings entry.
- The center is the narrative source of truth. It uses a readable maximum width for prose while
  approvals, validations, and change summaries may span the available center width.
- A 420-520px right inspector is persistent on wide screens when a file or run is selected. It has
  Changes, Run, and Context tabs. At narrower widths it becomes an overlay; the rail can collapse.
- The composer is sticky at the bottom, compact when empty, and grows only with content. Model,
  permissions, context, and send/stop remain aligned in one control row.

Minimum supported content viewport is 1024x700. The demo target is 1920x1080. No essential action
depends on hover, and keyboard focus is visible.

### Information hierarchy

Each turn has three visually distinct levels:

1. User request: a quiet tinted block with no oversized card chrome.
2. Agent activity: plan checkpoints and grouped tool receipts. Routine reads/searches collapse into
   one line; writes, commands, failures, validations, and approvals remain distinct.
3. Agent final answer: always expanded prose after a full-width divider. It is never placed in a
   constrained nested scroll area.

An activity summary shows a verb, subject, state, and duration. Expansion reveals complete tool
name, normalized target, key arguments, cwd/command, approval source, structured result, truncation,
exit code, duration, and error. Hidden model reasoning is never requested or rendered.

Approvals are inline and visually anchored to the action. Write approvals show the proposed diff;
command approvals show the exact command and cwd. Denial is a normal recoverable state.

After completion, a compact evidence footer shows final state, validation status, changed file
count, tool count, requests/retries, steps used/max, context usage, compactions, and elapsed time.
Metrics that are unavailable are omitted rather than invented.

### Management center

Model, Permissions, Steps, Memory, Skills, Context, Help, and raw-result display use one consistent
sheet/drawer framework. Read-only inspection remains available while the Agent is busy; mutations
are disabled with an explanation. Destructive Memory actions require an explicit confirmation.

Slash commands execute locally through this management layer and are never sent to the model.
Argument completion is anchored to the composer, spans its usable width, uses the same surface
color across command and description columns, supports arrows/Enter/Escape, and adapts to available
height without hard-coded terminal-like widths.

## Visual system

- Warm neutral Apple/Google-inspired hierarchy with restrained blue selection, green verified
  success, amber approval, and red failure/destructive intent.
- Bundled Noto Sans SC for UI and Chinese/Latin prose; bundled JetBrains Mono for code, paths,
  commands, model IDs, metrics, and diffs.
- A 4px base spacing scale, one-pixel separators, 8-14px radii, limited shadows, and no dashboard
  grid of large generic cards.
- Light theme is the video default. Dark theme follows system settings after light-theme acceptance.
- User request, activities, final output, completion palette, and inspector share consistent spacing
  and dynamically consume available width; no fixed decorative horizontal-line lengths.

## History, changes, and safety

`SessionStore` remains the source of truth. Restoring a conversation uses durable final messages and
structured records, ignores historical deltas, repairs incomplete tool calls as interrupted, and
never replays side effects. Gemini thought signatures remain attached to
`extra_content.google.thought_signature` through persistence and compaction.

Changed-file review remains read-only. It displays normalized paths, status, cumulative additions
and deletions, applied diffs, and bounded before/after information available from existing change
records. Undo is not claimed until a durable conflict-safe reverse-diff workflow exists.

All preview and completion paths pass through `WorkspacePaths`. Absolute paths, traversal, escaping
links/junctions, binaries, and text larger than 2 MiB are rejected. Renderer requests cannot execute
tools directly. API keys remain in environment variables or ignored local configuration and are
never returned to Electron.

## Error and recovery behavior

- Python startup failure: show the stage, sanitized process message, selected interpreter, and a
  retry/choose-interpreter action; no Agent side effect occurred.
- Provider/model failure: keep the user turn, show whether any tool side effects already occurred,
  and allow retry after model settings change.
- Tool failure: retain the audited call, result/error, exit code or timeout, and allow the Agent to
  continue or the user to cancel.
- Renderer disconnect or window close: deny pending approvals and cancel the active turn.
- Protocol mismatch: fail closed with a rebuild/restart instruction.
- Workspace switch failure: keep the existing workspace and conversation active.

## Testing and comparison

### Automated

- Python unit tests for all new request validation, management services, busy-state rejection,
  lifecycle transitions, secret filtering, and shutdown.
- React Testing Library and Vitest for every management surface, completion interaction, activity
  grouping, approvals, final-answer expansion, responsive layout state, and error recovery.
- Electron main/preload tests around argument construction, startup handshake parsing, navigation
  policy, workspace switching, and child cleanup.
- Playwright Electron tests at 1024x700 and 1920x1080 covering launch, new/resume session, send,
  streaming, completion, stop, approval decisions, management actions, diff inspection, and close.
- Existing Python and V1-compatible tests remain green. Ruff, Ruff format, strict mypy, TypeScript,
  Vitest, Playwright, and production builds are required before handoff.

### Real-model validation

If configured credentials are present, validation uses the actual selected Gemini-compatible model
through the production gateway. It runs only in a disposable, path-verified directory inside the
V2 worktree. The directory contains a scoped `AGENTS.md`, a small failing test, and no repository
credentials. The scenario covers read, visible plan, approval-gated edit, approval-gated focused
test, correction if needed, final evidence, a follow-up turn without side-effect replay, session
resume, and context inspection. Artifacts remain ignored for manual review.

No test output records secrets or raw environment values. A mock E2E run is reported as mock; it
never substitutes for a failed or unavailable real-model run.

### Visual comparison delivery

The handoff includes:

- independent V1 Web and V2 Electron launch commands,
- matching 1024x700 and 1920x1080 screenshots using the same semantic fixture,
- a short parity matrix identifying every TUI capability and its V2 location,
- the real-model test record or an explicit unavailable/failure report,
- no merge or push unless the user later authorizes it.

## Exit criteria

V2 is ready for user comparison only when:

1. All TUI capabilities in the parity table are implemented or explicitly marked inapplicable with
   an equivalent desktop outcome.
2. A complete turn can stream, request approval, modify a file, run validation, cancel, finish, and
   resume without replaying side effects.
3. Final Agent output is always expanded; routine activities are concise but fully auditable.
4. The UI remains coherent at 1024x700 and fills a 1920x1080 window without fixed-width gaps.
5. Electron renderer has no generic filesystem, shell, environment, or credential authority.
6. V1 remains untouched and launchable for direct comparison.
7. Required automated checks pass and the validation evidence contains no secret material.

