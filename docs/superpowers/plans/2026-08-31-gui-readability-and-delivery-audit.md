# GUI Readability and Delivery Audit Implementation Plan

> **Status (2026-08-31):** Implemented and audited. Static analysis, type checking, coverage,
> and evaluation-fixture validation pass; sandbox-blocked package/frontend process checks remain
> explicit handoff gates.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the desktop review-surface overlap and readability regressions, then synchronize every maintained delivery document with the actual Forge implementation and assessment requirements.

**Architecture:** Keep behavior in the existing React components and consolidate visual rules in the established theme without changing the local Python authority boundary. Treat source, protocol types, tests, and the assessment PDF as facts; documentation may describe only behavior supported by those facts.

**Tech Stack:** React 19, TypeScript 5.9, Vitest, CSS, Electron 44, Python 3.11/3.12, FastAPI loopback gateway, Ruff, mypy, pytest.

**Spec:** `ref/推免考核题目学生版.pdf`, `AGENTS.md`, and the user's GUI review notes in the active acceptance session.

## Global Constraints

- Preserve the existing dirty worktree and do not remove or rewrite unrelated user changes.
- Keep the Electron renderer sandboxed and keep model, tool, filesystem, approval, Session, Memory, and Skill authority in Python.
- Do not expose or persist credentials, raw protocol JSON, hidden chain-of-thought, or workspace-external resources.
- Keep Python 3.11/3.12 and Windows/Linux support.
- Every user action must receive visible feedback, with reduced-motion behavior where animation is used.
- `README.txt` must stay within 1000 Chinese characters and include the public repository URL before final submission.

---

### Task 1: Stabilize the change-review layout

**Files:**
- Modify: `web/src/app/theme.css`
- Test: `web/src/components/ChangeReviewPane.test.tsx`
- Test: `web/src/components/DiffViewer.test.tsx`

**Interfaces:**
- Consumes: `ChangeReviewPane`, `DiffViewer`, `.diff-toolbar`, `.diff-scroll`, and `.side-diff-scroll`.
- Produces: a non-shrinking, content-sized toolbar followed by a scroll-confined Diff body.

- [x] **Step 1: Confirm the regression surface**

Inspect the portal pane DOM order and CSS cascade. The toolbar must precede the Diff body, wrap controls when necessary, and remain in normal flex layout.

- [x] **Step 2: Add the layout invariant**

Give the pane toolbar `flex: 0 0 auto`, an opaque review-surface background, and its own stacking level. Give only the Diff body `flex: 1 1 auto`, `min-height: 0`, and scrolling.

- [x] **Step 3: Run focused checks**

Run `npm test -- ChangeReviewPane.test.tsx DiffViewer.test.tsx` from `web/`, followed by `npm run typecheck`.

### Task 2: Improve desktop readability and hierarchy

**Files:**
- Modify: `web/src/app/theme.css`
- Modify: `web/src/components/CommandGuide.tsx`
- Modify: `web/src/components/ResourceFileTree.tsx`
- Test: `web/src/components/Composer.test.tsx`
- Test: `web/src/components/ResourcePreviewPane.test.tsx`

**Interfaces:**
- Consumes: root color tokens, composer metadata, command guide items, inspector tabs, code/Diff surfaces, and resource tree nodes.
- Produces: WCAG-readable secondary text, a row-oriented command guide, thin code scrollbars, stable code line spacing, stronger active tabs, and directory guide lines.

- [x] **Step 1: Establish readable text tokens**

Replace low-contrast `--muted` and `--faint` values with colors that retain visible hierarchy while meeting normal-text contrast on Forge's light surfaces. Apply explicit readable colors to placeholders, composer metadata, resource empty states, and tree status metadata.

- [x] **Step 2: Clarify command rows**

Render Slash commands in one row per command with a stable command column, description column, subtle separators, alternating surfaces, and a hover/focus state. Wrapped descriptions must remain visually attached to their command.

- [x] **Step 3: Refine code and navigation surfaces**

Use the shared code font, 1.6 line height, stable line-number padding, and thin overlay-style scrollbars for Diff, command, and file previews. Strengthen the active inspector tab with font weight and a two-or-more-pixel indicator.

- [x] **Step 4: Add resource tree guides**

Mark child groups with depth metadata and draw non-interactive guide lines without changing button semantics or selection behavior.

- [x] **Step 5: Run focused checks**

Run the component tests that cover composer controls, command rendering, file tree/preview, and Diff review, then run `npm run typecheck`.

### Task 3: Audit implementation and delivery claims

**Files:**
- Read: `src/coding_agent/**/*.py`
- Read: `web/src/**/*.tsx`
- Read: `tests/**/*.py`
- Read: `web/**/*.test.ts*`
- Read: `.github/workflows/ci.yml`
- Read: `ref/推免考核题目学生版.pdf`

**Interfaces:**
- Consumes: exported CLI commands, runtime defaults, protocol commands, GUI controls, security boundaries, and executable verification scripts.
- Produces: a claim matrix of implemented, deferred, and manually unverified behavior.

- [x] **Step 1: Inventory public surfaces**

Cross-check headless commands, Electron startup, model/provider setup, symbol tools, verification hooks, Session/Memory/Skill behavior, change review, and workspace trust against code and tests.

- [x] **Step 2: Inventory assessment obligations**

Confirm deadline, repository-history rules, credential restrictions, `README.txt` limit/content, and video duration/format/size directly from the two-page assessment PDF.

- [x] **Step 3: Record only supported claims**

Classify real-model evaluation, clean-clone acceptance, video capture, installer/signing, and release tagging as pending until fresh evidence exists.

### Task 4: Synchronize all maintained documentation

**Files:**
- Modify: `README.md`
- Modify: `README.txt`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/demo-script.md`
- Modify: `SECURITY.md`
- Modify: `evals/README.md`
- Review: `docs/superpowers/specs/*.md`
- Review: `docs/superpowers/plans/*.md`

**Interfaces:**
- Consumes: Task 3's claim matrix.
- Produces: consistent setup, feature, architecture, security, evaluation, progress, and demo documentation.

- [x] **Step 1: Rewrite the assessment README**

Keep `README.txt` under 1000 Chinese characters. Include a repository-address placeholder only if the repository URL cannot be discovered locally, the exact Electron launch commands, key differentiators, safety boundary, and credential policy.

- [x] **Step 2: Correct the primary README**

Align installation extras, desktop startup, provider management, commands, symbol tools, verification hooks, review semantics, and verification commands with current code and package scripts.

- [x] **Step 3: Correct supporting documents**

Update architecture for the current review pane, connection lifecycle, provider model, symbol index, and verification flow. Update roadmap and demo script to distinguish implemented behavior from required manual acceptance. Expand security and evaluation notes only where code supports the statement.

- [x] **Step 4: Mark historical design records**

Do not rewrite dated design history as current documentation. Add or preserve clear status pointers when an old plan/spec has been superseded by Electron delivery.

### Task 5: Verify and self-review the release candidate

**Files:**
- Review: all changed source, test, documentation, and generated static asset files.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: fresh verification evidence and a final list of remaining manual gates.

- [ ] **Step 1: Verify the renderer**

Run from `web/`: `npm test`, `npm run build`, `npm run desktop:build`, and `npm run test:e2e` when the environment permits browser startup.

- [ ] **Step 2: Verify Python and packaging**

Run from the repository root: `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy`, full branch-coverage pytest, `python scripts/check_coverage.py coverage.json`, `python evals/run_eval.py --dry-run`, and `python -m build`.

- [ ] **Step 3: Verify documentation and repository hygiene**

Run `git diff --check`, count `README.txt`, scan tracked files for secret-like values and generated artifacts, and compare built renderer assets with `src/coding_agent/web/static`.

- [ ] **Step 4: Review every claim and remaining gate**

Read the final diff independently. Report test commands with exit codes, environment-blocked checks, and the remaining real-model/video/clean-clone work without presenting them as complete.

## Verification evidence

- Passed: Ruff check, Ruff format check, strict mypy, renderer TypeScript typecheck, Electron
  TypeScript build, `git diff --check`, coverage gate (86.05%), and evaluation fixture dry-run.
- Python suite: 329 tests passed. The two package-content tests were blocked before their assertions
  because this execution sandbox denied the nested `python -m build` process permission to create a
  temporary virtual environment.
- Renderer suite/build: source typecheck and Electron compilation pass. Vitest/Vite cannot start
  `esbuild` in this sandbox (`spawn EPERM`); the production static entry was separately checked to
  reference existing hashed assets containing the final layout rules.
- Still manual: clean-clone Windows/Linux acceptance, the real-model three-runs-per-case evaluation,
  the final two-minute video, and CI on the exact candidate commit.
