# Session Verification Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver session-isolated deterministic verification with explicit modes, user procedures,
durable evidence, focused rule selection, and correct Electron GUI status and ordering.

**Architecture:** Store the active verification contract and results as append-only SessionStore
records, while retaining workspace rules only as importable templates. AgentController owns rule
selection and execution semantics; RuntimeManagement exposes the active session contract; the web
coordinator transports durable events and the React store renders exact backend states.

**Tech Stack:** Python 3.11/3.12, Pydantic, JSONL SessionStore, pytest, React 19, TypeScript,
Zustand, Vitest, Testing Library, Electron.

**Spec:** `docs/superpowers/specs/2026-08-31-session-verification-contract-design.md`

**Status:** Implemented and verified on 2026-08-31. The checklist below preserves the original
test-first execution sequence; release evidence is recorded in the repository handoff and current
README/architecture/roadmap documents.

## Global Constraints

- Preserve workspace confinement, approvals, hard safety rules, cancellation, timeout, and Step
  accounting for every verification command.
- Never persist provider credentials or expose hidden reasoning.
- Keep workspace `max_steps` project-scoped; make verification mode, rules, procedures, and results
  session-scoped.
- Do not change unrelated presentation surfaces in this module.
- Use test-first RED/GREEN cycles and run the full Python and web verification matrix before handoff.

---

### Task 1: Session verification data model and replay

**Files:**
- Create: `src/coding_agent/verification.py`
- Modify: `src/coding_agent/session.py`
- Modify: `src/coding_agent/controller.py`
- Test: `tests/test_session.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Produces: `VerificationMode`, `VerificationProcedure`, `VerificationContract`,
  `VerificationResultRecord`, `restore_verification_contract(records)`, and
  `restore_verification_results(records)`.
- Persists: `verification_config` and `verification_result` JSONL records.

- [ ] Write failing tests showing that two sessions in one workspace have independent contracts,
  a resumed session restores its latest contract, an empty Agent TDD contract is valid, and deleting
  a session removes its verification records.
- [ ] Run the focused tests and confirm they fail because configuration still comes from the
  workspace store.
- [ ] Implement the immutable Pydantic models and replay helpers, then make AgentController restore
  the latest contract from its own session.
- [ ] Run the focused tests and keep legacy workspace parsing as template-only compatibility.

### Task 2: Runtime management, protocol, and Agent registration

**Files:**
- Modify: `src/coding_agent/runtime.py`
- Modify: `src/coding_agent/runtime_management.py`
- Modify: `src/coding_agent/tools/base.py`
- Modify: `src/coding_agent/tools/verification.py`
- Modify: `src/coding_agent/web/protocol.py`
- Modify: `src/coding_agent/web/app.py`
- Test: `tests/test_runtime_management.py`
- Test: `tests/test_verification_tool.py`
- Test: `tests/web/test_protocol.py`
- Test: `tests/web/test_app.py`

**Interfaces:**
- Consumes: `AgentController.set_verification_contract(contract)` and
  `AgentController.register_verification_check(check)`.
- Produces: runtime snapshot fields `mode`, `checks`, `procedures`, `suggestions`, and
  `workspace_templates`; request `verification.set` accepts the same contract fields.

- [ ] Write failing tests for empty Agent TDD save, session-only updates, procedure validation,
  template import data, and Agent registration persistence.
- [ ] Run focused tests and confirm current workspace mutation and boolean mode fail them.
- [ ] Route management changes to the active controller/session and make the registration tool
  upsert into that session without mutating workspace settings.
- [ ] Run focused tests and retain legacy request fields only as input migration.

### Task 3: Prompt contract and deterministic ownership

**Files:**
- Modify: `src/coding_agent/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: active `VerificationContract` and its enabled procedures.
- Produces: a stable system-prompt section that tells Agent TDD to write separate tests, call
  `register_verification`, and leave execution to the deterministic layer.

- [ ] Write failing tests for procedure injection, empty Agent TDD guidance, and suppression of
  direct duplicate execution of an exactly registered verification command.
- [ ] Run tests and verify prompt/ownership failures.
- [ ] Add the contract prompt section and controller guard while allowing unrelated diagnostic
  commands.
- [ ] Run controller tests.

### Task 4: Turn-scoped selection, durable results, and timing

**Files:**
- Modify: `src/coding_agent/change_ledger.py`
- Modify: `src/coding_agent/controller.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Test: `tests/test_change_ledger.py`
- Test: `tests/test_controller.py`
- Test: `tests/web/test_coordinator.py`

**Interfaces:**
- Produces: change records with `turn_id`; `run_verification(turn_id)` filters checks using that
  turn's paths; verification result records preserve terminal status, rule data, timing, and output.

- [ ] Write failing tests for read-only turns, no-applicable-rule results, target filtering, manual
  turn validation, result replay, approval-wait timing, and execution timing.
- [ ] Run tests and confirm the broad manual execution and transient result behavior fail.
- [ ] Add turn ownership to changes, shared selection helpers, durable result append, and distinct
  approval/running lifecycle events.
- [ ] Run the focused backend tests.

### Task 5: Structured suggestions and legacy import

**Files:**
- Modify: `src/coding_agent/runtime_management.py`
- Test: `tests/test_runtime_management.py`

**Interfaces:**
- Produces: `VerificationSuggestion` with `label`, `kind`, `command`, `cwd`, `target_paths`, and
  `scope` (`focused` or `full_project`).

- [ ] Write failing tests for a nested Python project, a nested package.json project, root fallback,
  de-duplication, and legacy workspace rules exposed only as templates.
- [ ] Run tests and confirm command-only suggestions fail.
- [ ] Implement bounded marker scanning and structured suggestions without auto-selecting root-wide
  checks when a focused check exists.
- [ ] Run runtime-management tests.

### Task 6: Web event semantics and response ordering

**Files:**
- Modify: `src/coding_agent/web/presenter.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `web/src/state/store.ts`
- Test: `tests/web/test_presenter.py`
- Test: `tests/web/test_coordinator.py`
- Test: `web/src/state/store.test.ts`

**Interfaces:**
- Preserves all verification terminal statuses.
- Separates `command_test` from deterministic `validation`.
- Renders tool-bearing assistant text as a trace note, not final output.

- [ ] Write failing backend/frontend tests for every terminal status, explicit evidence only,
  approval/running labels, durable replay, and tool-text ordering.
- [ ] Run focused tests and observe flattening/misclassification failures.
- [ ] Implement exact event mapping and ordering projection.
- [ ] Run focused tests.

### Task 7: GUI verification contract editor and outcome actions

**Files:**
- Modify: `web/src/components/ContextDrawer.tsx`
- Modify: `web/src/components/Timeline.tsx`
- Modify: `web/src/components/verificationEvidence.ts`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/app/theme.css`
- Test: `web/src/app/App.transport.test.tsx`
- Test: `web/src/components/Timeline.test.tsx`
- Test: `web/src/components/verificationEvidence.test.ts`

**Interfaces:**
- Presents three exclusive modes: `关闭`, `规则验证`, `Agent TDD`.
- Edits session rules and procedures, imports templates, and uses structured suggestions.
- Routes `test_failed` to Repair and `configuration_error`/`not_configured` to setup.

- [ ] Write failing tests for mode switching, empty TDD save, visible save feedback, procedure edit,
  structured suggestion cwd, status-specific copy/actions, and manual no-match setup behavior.
- [ ] Run the focused Vitest files and confirm failures.
- [ ] Replace the switch/checkbox hierarchy, implement progressive rule/procedure disclosure, and
  render exact validation states with accessible status text and reduced-motion-safe feedback.
- [ ] Run the focused Vitest files.

### Task 8: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `README.txt`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/demo-script.md`

- [ ] Replace project-scoped verification claims with session contract, modes, procedures,
  deterministic ownership, focused suggestions, and exact result semantics.
- [ ] Run `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy`, and the full
  pytest suite.
- [ ] Run `npm test`, `npm run build`, and `npm run desktop:build` from `web`.
- [ ] Inspect `git diff --check`, `git status --short`, and generated/static files; report any
  pre-existing or intentionally retained worktree changes separately.
