# Structured Verification and Model Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deterministic verification project-aware and stateful, and let users add sibling models without exposing or duplicating provider credentials.

**Architecture:** Replace bare verification command strings with workspace-relative check records while preserving migration from existing settings. Execute checks through the existing `run_command` safety path with a confined working directory and publish distinct registration, execution, and terminal states. A copied model remains under its source provider and reuses that provider's Base URL, compatibility mode, and operating-system credential; only its Model ID is new.

**Tech Stack:** Python 3.11/3.12, Pydantic, pytest, React, TypeScript, Vitest, Electron IPC.

**Spec:** Approved design from the 2026-08-31 verification audit in the active user session.

> Superseded scope note: cross-provider credential-copy work is retained only as internal compatibility code; the current UI copies a model within its existing provider. Active verification state
> is no longer project-global; the later Session Verification Contract stores mode, rules,
> procedures, and results per Session while retaining workspace rules only as importable templates.

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

- [x] Write failing round-trip, migration, and validation tests.
- [x] Run the focused tests and confirm failures describe the missing check model.
- [x] Implement the minimal Pydantic models and runtime snapshot mapping.
- [x] Run the focused tests to green.

### Task 2: Confined command working directories

**Files:**
- Modify: `src/coding_agent/tools/command.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: workspace-relative `cwd` from a verification check.
- Produces: `run_command({command, cwd, timeout})`, with approval text and results containing the resolved relative directory.

- [x] Write failing tests for nested cwd execution and traversal rejection.
- [x] Run the focused tests and confirm the command still executes at workspace root.
- [x] Resolve cwd through `WorkspacePaths` and include it in approval/result metadata.
- [x] Run the focused tests to green.

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

- [x] Write failing tests for cwd propagation, error classification, and non-repairable failures.
- [x] Run the focused tests and confirm expected failures.
- [x] Implement check execution and publish structured start/finish evidence.
- [x] Strengthen Agent TDD instructions around project roots and separate test artifacts.
- [x] Run the focused tests to green.

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

- [x] Write failing reducer and interaction tests.
- [x] Run the focused Vitest files and confirm expected failures.
- [x] Implement rule-row editing and status presentation using existing design tokens.
- [x] Run the focused Vitest files to green.

### Task 5: Same-provider model copy without secret movement

**Files:**
- Modify: `web/src/components/ModelManager.tsx`
- Modify: `web/src/app/App.tsx`
- Test: `web/src/components/ModelManager.test.tsx`
- Test: `web/src/app/App.transport.test.tsx`

**Interfaces:**
- Produces: a sibling model entry under the selected provider.
- Consumes: the source provider's name, Base URL, compatibility mode, and existing credential reference;
  only the new Model ID is editable.

- [x] Write a failing component test proving copy locks provider/Base URL and clears Model ID.
- [x] Write a failing integration test proving no credential-copy bridge call occurs.
- [x] Reuse the existing provider metadata and credential reference while adding the new model.
- [x] Run ModelManager and App integration tests to green.

### Task 6: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `README.txt`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/demo-script.md`

**Interfaces:**
- Documents: nested project cwd rules, verification outcomes, TDD responsibility split, and secure model-copy behavior.

- [x] Update documentation to match implemented behavior without overclaiming.
- [x] Run Ruff check and format verification.
- [x] Run strict mypy and the full pytest suite.
- [x] Run `npm test`, `npm run build`, and `npm run desktop:build` in `web`.
- [x] Review `git diff` for credentials, generated intermediates, and unrelated changes before handoff.

### Task 7: Agent-registered, change-aware verification

**Files:**
- Add: `src/coding_agent/tools/verification.py`
- Modify: `src/coding_agent/tools/base.py`
- Modify: `src/coding_agent/tools/registry.py`
- Modify: `src/coding_agent/tools/filesystem.py`
- Modify: `src/coding_agent/controller.py`
- Modify: `src/coding_agent/change_ledger.py`
- Modify: `web/src/state/store.ts`
- Modify: `web/src/components/Timeline.tsx`
- Test: `tests/test_verification_tool.py`
- Test: `tests/test_change_ledger.py`
- Test: `tests/test_controller.py`
- Test: `tests/test_safety_and_tools.py`
- Test: `web/src/state/store.test.ts`
- Test: `web/src/components/Timeline.test.tsx`

**Interfaces:**
- Produces: `register_verification({label, kind, command, cwd, timeout_seconds, target_paths})` in the default model tool schema.
- Persists: Agent-declared rules with an explicit workspace-relative project root and covered paths.
- Records: files and directories created during the current turn as registration evidence.
- Runs: only enabled checks whose target scope intersects files changed in the current turn.
- Presents: read-only turns as complete without offering irrelevant verification controls.

- [x] Write focused failing tests for registration, nested roots, artifacts, and change scoping.
- [x] Add the registration tool to the default registry and approval flow.
- [x] Persist registered checks and refresh the active controller without a restart.
- [x] Preserve created-directory evidence in the durable change ledger.
- [x] Distinguish read-only turns from changed-but-unverified turns in the GUI.
- [x] Run the full Python and Electron verification matrix after documentation is synchronized.
