# Structured Verification and Model Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deterministic verification project-aware and stateful, and make model-copy operations duplicate credentials safely without exposing API keys to the renderer or protocol.

**Architecture:** Replace bare verification command strings with workspace-relative check records while preserving migration from existing settings. Execute checks through the existing `run_command` safety path with a confined working directory and publish distinct approval, execution, and terminal states. Add a main-process credential-copy transaction that reads and writes only through the secure credential bridge; the renderer supplies provider identifiers but never receives the secret.

**Tech Stack:** Python 3.11/3.12, Pydantic, pytest, React, TypeScript, Vitest, Electron IPC.

**Spec:** Approved design from the 2026-08-31 verification audit in the active user session.

## Global Constraints

- Preserve the existing command safety classifier, approval policy, cancellation, and workspace confinement.
- Never place credentials in renderer state, WebSocket traffic, sessions, Memory, logs, or `models.toml`.
- Existing `verification.commands: list[str]` settings migrate to checks with `cwd = "."`.
- Verification working directories are workspace-relative directories resolved through `WorkspacePaths`.
- Agent TDD writes framework-native tests and declares checks; deterministic verification owns automatic execution.
- Support Windows and Linux on Python 3.11 and 3.12.

---

### Task 1: Structured verification settings

**Files:**
- Modify: `src/coding_agent/workspace_settings.py`
- Modify: `src/coding_agent/runtime_management.py`
- Test: `tests/test_workspace_settings.py`
- Test: `tests/test_runtime_management.py`

**Interfaces:**
- Produces: `VerificationCheck` with `id`, `label`, `kind`, `command`, `cwd`, `timeout_seconds`, and `enabled`.
- Produces: backward-compatible migration from legacy command strings.

- [ ] Write failing round-trip, migration, and validation tests.
- [ ] Run the focused tests and confirm failures describe the missing check model.
- [ ] Implement the minimal Pydantic models and runtime snapshot mapping.
- [ ] Run the focused tests to green.

### Task 2: Confined command working directories

**Files:**
- Modify: `src/coding_agent/tools/command.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: workspace-relative `cwd` from a verification check.
- Produces: `run_command({command, cwd, timeout})`, with approval text and results containing the resolved relative directory.

- [ ] Write failing tests for nested cwd execution and traversal rejection.
- [ ] Run the focused tests and confirm the command still executes at workspace root.
- [ ] Resolve cwd through `WorkspacePaths` and include it in approval/result metadata.
- [ ] Run the focused tests to green.

### Task 3: Verification engine outcomes and TDD contract

**Files:**
- Modify: `src/coding_agent/controller.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `src/coding_agent/web/protocol.py`
- Test: `tests/test_controller.py`
- Test: `tests/web/test_coordinator.py`
- Test: `tests/web/test_protocol.py`

**Interfaces:**
- Consumes: ordered `VerificationCheck` records.
- Produces: per-check evidence and terminal categories `passed`, `test_failed`, `configuration_error`, `approval_denied`, `timed_out`, `cancelled`, and `not_configured`.

- [ ] Write failing tests for cwd propagation, error classification, and non-repairable failures.
- [ ] Run the focused tests and confirm expected failures.
- [ ] Implement check execution and publish structured start/finish evidence.
- [ ] Strengthen Agent TDD instructions around project roots and separate test artifacts.
- [ ] Run the focused tests to green.

### Task 4: Project-aware GUI verification editor and status

**Files:**
- Modify: `web/src/state/store.ts`
- Modify: `web/src/components/ContextDrawer.tsx`
- Modify: `web/src/components/Timeline.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/protocol/types.ts`
- Test: `web/src/state/store.test.ts`
- Test: `web/src/app/App.transport.test.tsx`
- Test: `web/src/components/Timeline.test.tsx`

**Interfaces:**
- Consumes: structured checks and verification events.
- Produces: editable rule rows and distinct waiting-approval/running/configuration-failure/test-failure states.

- [ ] Write failing reducer and interaction tests.
- [ ] Run the focused Vitest files and confirm expected failures.
- [ ] Implement rule-row editing and status presentation using existing design tokens.
- [ ] Run the focused Vitest files to green.

### Task 5: Secure credential copy for model duplication

**Files:**
- Modify: `web/electron/types.ts`
- Modify: `web/electron/preload.cts`
- Modify: `web/electron/main.ts`
- Modify: `web/electron/credentialTransactions.ts`
- Modify: `web/src/components/ModelManager.tsx`
- Modify: `web/src/app/App.tsx`
- Test: `web/electron/credentialTransactions.test.ts`
- Test: `web/src/app/App.transport.test.tsx`

**Interfaces:**
- Produces: `copyProviderCredential(sourceProvider, targetProvider)` returning transaction metadata only.
- Consumes: source and destination provider identifiers from the renderer; the secret remains in the Electron main process and Python credential bridge.

- [ ] Write a failing credential transaction test proving the destination receives the source secret without returning it.
- [ ] Write a failing UI integration test proving model copy invokes the credential-copy bridge before metadata persistence.
- [ ] Implement the minimal IPC/preload/transaction path.
- [ ] Commit on metadata success and roll back on failure.
- [ ] Run Electron and App tests to green.

### Task 6: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `README.txt`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/demo-script.md`

**Interfaces:**
- Documents: nested project cwd rules, verification outcomes, TDD responsibility split, and secure model-copy behavior.

- [ ] Update documentation to match implemented behavior without overclaiming.
- [ ] Run Ruff check and format verification.
- [ ] Run strict mypy and the full pytest suite.
- [ ] Run `npm test`, `npm run build`, and `npm run desktop:build` in `web`.
- [ ] Review `git diff` for credentials, generated intermediates, and unrelated changes before handoff.
