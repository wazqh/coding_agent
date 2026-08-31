# Durable GUI Operation and Review Implementation Plan

> **Status (2026-08-31):** Implemented in the current delivery candidate. Retained as an engineering
> record; fresh automated and manual release gates remain listed in `docs/roadmap.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a durable, compact GUI operation timeline, restart-safe change review, richer inspector, and bounded verification workflow.

**Architecture:** Thread the model tool-call ID through approval and result events, persist an append-only change ledger in session JSONL, and let the presenter project those records into normalized GUI operations. Add review and verification capabilities through existing WebSocket request handlers rather than introducing another service.

**Tech Stack:** Python 3.11/3.12, Pydantic, JSONL SessionStore, React 19, TypeScript, Zustand, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-durable-gui-operation-review-design.md`

## Global Constraints

- Preserve CLI/TUI compatibility and the local controller/tool loop.
- No raw JSON or hidden reasoning in user-facing UI.
- No credentials in events, sessions, logs, or frontend state.
- Hard safety rules cannot be overridden.
- Run the full Python and frontend suites because shared runtime, safety, persistence, and UI change.
- Preserve unrelated working-tree changes and do not commit or push without explicit authorization.

---

### Task 1: Stable operation identity

**Files:**
- Modify: `src/coding_agent/tools/base.py`
- Modify: `src/coding_agent/controller.py`
- Modify: `src/coding_agent/safety/approval.py`
- Test: `tests/test_controller.py`
- Test: `tests/test_safety_and_tools.py`

**Interfaces:**
- Produces: `ToolContext.operation_id: str | None`
- Produces: approval event `data.operation_id`
- Preserves: existing `ApprovalRequest.fingerprint` semantics

- [x] Add failing tests asserting approval request and decision events use the enclosing tool-call ID.
- [x] Run the targeted tests and confirm they fail because approval events lack `operation_id`.
- [x] Add `operation_id` to `ToolContext`, set it before each registry execution, and emit it with approval events.
- [x] Run targeted controller and safety tests.

### Task 2: Durable change ledger and safe bulk review

**Files:**
- Create: `src/coding_agent/change_ledger.py`
- Modify: `src/coding_agent/tools/base.py`
- Modify: `src/coding_agent/tools/filesystem.py`
- Modify: `src/coding_agent/controller.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `src/coding_agent/web/app.py`
- Modify: `src/coding_agent/web/protocol.py`
- Test: `tests/test_memory_session_context.py`
- Test: `tests/test_safety_and_tools.py`
- Test: `tests/web/test_coordinator.py`
- Test: `tests/web/test_app.py`

**Interfaces:**
- Produces: append-only record types `change`, `change_review`
- Produces: `TurnCoordinator.review_change(change_id, decision)`
- Produces: `TurnCoordinator.review_all_changes(decision)`

- [x] Add failing restore tests for created and modified files, reviewed state, and conflicting hashes.
- [x] Add failing coordinator tests for accept, reverse-order discard, and partial conflict reports.
- [x] Implement bounded ledger serialization/replay without persisting secrets or unbounded backups.
- [x] Append records when file tools record changes and rebuild ledger in controller restore.
- [x] Add WebSocket actions for single/all accept and discard.
- [x] Run ledger, coordinator, and app tests.

### Task 3: One operation card and exploration grouping

**Files:**
- Modify: `src/coding_agent/web/presenter.py`
- Modify: `web/src/protocol/types.ts`
- Modify: `web/src/state/store.ts`
- Modify: `web/src/components/Timeline.tsx`
- Modify: `web/src/components/ActivityRow.tsx`
- Modify: `web/src/components/icons.tsx`
- Modify: `web/src/app/theme.css`
- Test: `tests/web/test_presenter.py`
- Test: `web/src/state/store.test.ts`
- Test: `web/src/components/Timeline.test.tsx`

**Interfaces:**
- Consumes: stable `operation_id`
- Produces: idempotent `activity.updated` events keyed by operation ID
- Produces: compact exploration group for consecutive successful read-only operations

- [x] Add failing presenter/store tests for approval-to-result in-place updates.
- [x] Add failing timeline tests for exploration grouping and hard-block shield treatment.
- [x] Normalize approval/tool events into one operation projection and preserve expanded state.
- [x] Group only successful routine read operations; keep mutations, validation, and failures visible.
- [x] Replace hard-block `×` with an accessible shield and improved copy.
- [x] Run presenter, store, and timeline tests.

### Task 4: Change review inspector

**Files:**
- Modify: `web/src/components/ChangesSummary.tsx`
- Modify: `web/src/components/DiffViewer.tsx`
- Create: `web/src/components/SideBySideDiff.tsx`
- Modify: `web/src/components/ContextDrawer.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/app/theme.css`
- Test: `web/src/components/DiffViewer.test.tsx`
- Test: `web/src/app/App.transport.test.tsx`

**Interfaces:**
- Consumes: single/all review WebSocket actions
- Produces: persisted drawer width preference
- Produces: unified/side-by-side/enlarged view state

- [x] Add failing tests for accept/discard controls, view switching, enlarged review, and resize clamping.
- [x] Add review controls with clear pending/reviewed/conflicted states.
- [x] Implement side-by-side parsing from unified diff and enlarged in-app review mode.
- [x] Implement pointer/keyboard accessible resize handle and persist width locally.
- [x] Run Diff and transport tests.

### Task 5: Run, resources, and context delivery

**Files:**
- Modify: `src/coding_agent/tokens.py`
- Modify: `src/coding_agent/context.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `src/coding_agent/web/presenter.py`
- Modify: `web/src/protocol/types.ts`
- Modify: `web/src/state/store.ts`
- Modify: `web/src/components/ContextDrawer.tsx`
- Modify: `web/src/app/theme.css`
- Test: `tests/test_tokens.py`
- Test: `tests/web/test_presenter.py`
- Test: `web/src/state/store.test.ts`

**Interfaces:**
- Produces: approximate `context_breakdown` categories
- Produces: normalized command/validation history and turn resource list

- [x] Add failing tests for category totals, command history, and read/touched resource collection.
- [x] Extend token estimation to return an approximate category breakdown without changing compaction thresholds.
- [x] Project structured run and resource history from persisted events.
- [x] Render consistent `used / window` metrics and human-readable history without Raw JSON.
- [x] Run token, presenter, and store tests.

### Task 6: Project verification hooks

**Files:**
- Modify: `src/coding_agent/workspace_settings.py`
- Modify: `src/coding_agent/controller.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `web/src/components/ContextDrawer.tsx`
- Test: `tests/test_workspace_settings.py`
- Test: `tests/test_controller.py`
- Test: `tests/web/test_coordinator.py`

**Interfaces:**
- Produces: project-scoped `verification.enabled`, `verification.agent_tdd`, and
  `verification.commands: list[str]`
- Produces: manual deterministic checks plus a bounded automatic repair loop with at most two retries

- [x] Add failing configuration tests for validation, project isolation, and malformed commands.
- [x] Add failing controller tests for no-change, pass, failure-feedback, retry limit, cancellation, and approval paths.
- [x] Execute hooks through existing command policy after a changed turn and emit normalized validation events.
- [x] Feed failures back within the existing step budget and stop after two repair attempts.
- [x] Split command history from verification controls; render manual/automatic states, Agent TDD
  guidance, deterministic results, and the evidence-fed repair action.
- [x] Derive conservative command suggestions from workspace project markers and keep them inert
  until the user explicitly adds and saves them.
- [x] Run workspace, controller, and coordinator tests.

### Task 7: Durable session titles and final verification

**Files:**
- Modify: `src/coding_agent/session.py`
- Modify: `src/coding_agent/controller.py`
- Modify: `web/src/state/store.ts`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Test: `tests/test_memory_session_context.py`
- Test: `web/src/state/store.test.ts`

**Interfaces:**
- Produces: persisted `session_title` record and deterministic local title normalizer

- [x] Add failing tests for concise titles, explicit title precedence, legacy fallback, and non-ASCII input.
- [x] Persist a normalized title after the first completed turn and expose it from `SessionStore.list()`.
- [x] Update frontend session state and user documentation.
- [x] Run Ruff check/format, strict mypy, full pytest, frontend tests, typecheck, Vite build, Electron build, and `git diff --check`.

### Task 8: Safe recent-project removal

**Files:**
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `src/coding_agent/web/app.py`
- Modify: `src/coding_agent/web/protocol.py`
- Modify: `web/src/components/SessionRail.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/app/theme.css`
- Test: `tests/web/test_coordinator.py`
- Test: `tests/web/test_app.py`
- Test: `web/src/components/SessionRail.test.tsx`

**Interfaces:**
- Produces: `project.remove` request that removes only Forge's recent-project index entry
- Preserves: workspace files, Git data, sessions, and project Memory

- [x] Add failing tests proving project removal updates the recent-project list without deleting the directory or its session and Memory files.
- [x] Add a project-row menu and confirmation dialog that displays the exact workspace path.
- [x] Remove the project from local UI/runtime metadata and select a safe remaining project.
- [x] Run coordinator, app, and SessionRail tests.
