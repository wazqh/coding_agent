# Local Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a polished localhost React frontend over the existing Forge Coding Agent core while preserving CLI/TUI behavior and safety boundaries.

**Architecture:** Extract frontend-neutral runtime construction, then place a typed loopback gateway between `AgentController` and a bundled React renderer. A semantic presenter converts raw agent events into a stable, versioned timeline protocol; the renderer never receives arbitrary tool or filesystem authority.

**Tech Stack:** Python 3.11/3.12, Pydantic, FastAPI/Starlette, Uvicorn, React, TypeScript, Vite, Zustand, Radix, Vitest, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-29-local-web-ui-design.md`

## Global Constraints

- Preserve existing CLI, TUI, JSONL, sessions, Gemini thought signatures, compaction, model switching, and workspace max-steps behavior.
- Keep Web dependencies optional and lazily imported only by `coding-agent web`.
- Bind only to loopback and never expose API keys or unrestricted tool/file/shell APIs.
- Keep all user-facing product names sourced from `coding_agent.branding`.
- Support Windows and Linux on Python 3.11 and 3.12.
- Use test-first red/green/refactor for every behavior change.
- Each task ends with a focused commit; pushing requires explicit user authorization.

---

### Task 1: Share frontend-neutral runtime construction

**Files:**
- Create: `src/coding_agent/runtime.py`
- Modify: `src/coding_agent/cli.py`
- Test: `tests/test_runtime.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `RuntimeFactory.create(session_id: str | None = None) -> AgentController`
- Produces: `RuntimeFactory.controller_factory() -> Callable[[str | None], AgentController]`
- Consumes: event and approval callbacks without importing Rich or any Web package.

- [ ] **Step 1: Write failing RuntimeFactory parity tests**

  Cover persisted provider selection, workspace max-steps override, trusted project resources,
  event callback identity, and a fresh ApprovalPolicy for every controller.

- [ ] **Step 2: Run the focused tests and verify RED**

  Run: `python -m pytest tests/test_runtime.py -q`

  Expected: collection fails because `coding_agent.runtime` does not exist.

- [ ] **Step 3: Implement RuntimeFactory**

  The constructor accepts resolved workspace, data directory, permissions, trust,
  interactivity, optional model name, event sink, approval callback, and environment mapping.
  It loads current model catalog/selection behavior and exposes configured `settings`,
  `model`, `model_manager`, and `sessions` without rendering concerns.

- [ ] **Step 4: Move CLI construction onto RuntimeFactory**

  Keep `_build_runtime()` as the compatibility adapter returning the same tuple while Rich
  renderer and terminal approval remain in `cli.py`.

- [ ] **Step 5: Run focused and full Python tests**

  Run: `python -m pytest tests/test_runtime.py tests/test_cli.py tests/test_cli_extended.py -q`

  Run: `python -m pytest -q`

- [ ] **Step 6: Commit**

  `git commit -m "refactor(runtime): share frontend runtime construction"`

### Task 2: Define semantic events and thread-safe approval

**Files:**
- Create: `src/coding_agent/web/__init__.py`
- Create: `src/coding_agent/web/protocol.py`
- Create: `src/coding_agent/web/presenter.py`
- Create: `src/coding_agent/web/approval.py`
- Test: `tests/web/test_protocol.py`
- Test: `tests/web/test_presenter.py`
- Test: `tests/web/test_approval.py`

**Interfaces:**
- Produces: Pydantic discriminated request and view-event models with
  `protocol_version`, `request_id`, `seq`, `session_id`, and `turn_id`.
- Produces: `AgentEventPresenter.present(event: AgentEvent) -> list[ViewEvent]`.
- Produces: `ApprovalBroker.request(request: ApprovalRequest) -> ApprovalDecision` and
  `resolve(approval_id: str, decision: ApprovalDecision) -> bool`.

- [ ] **Step 1: Write protocol validation tests**

  Assert unknown request types, empty request IDs, oversized task text, invalid session IDs,
  and illegal approval decisions are rejected without echoing their payload.

- [ ] **Step 2: Verify protocol tests fail**

  Run: `python -m pytest tests/web/test_protocol.py -q`

- [ ] **Step 3: Implement protocol models and encoder**

  Use a closed request union for initialize, session list/create/resume, turn start/cancel,
  approval resolution, file preview, changes list, and config get.

- [ ] **Step 4: Write and verify failing presenter tests**

  Cover TEXT buffering, tool call/result pairing by ID, read/search aggregation, plan state,
  errors, usage, completion, and history restoration that ignores historical deltas.

- [ ] **Step 5: Implement the minimal presenter**

  Preserve raw result data behind an expandable detail field while emitting concise Chinese
  labels for the default timeline.

- [ ] **Step 6: Write and verify failing ApprovalBroker tests**

  Exercise allow once, allow session, deny, unknown ID, double resolve, cancellation,
  disconnect, and close-all behavior with a real worker thread.

- [ ] **Step 7: Implement ApprovalBroker and run all Task 2 tests**

  Run: `python -m pytest tests/web/test_protocol.py tests/web/test_presenter.py tests/web/test_approval.py -q`

- [ ] **Step 8: Commit**

  `git commit -m "feat(web): add typed events and approval broker"`

### Task 3: Add the authenticated loopback gateway and CLI command

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/coding_agent/cli.py`
- Create: `src/coding_agent/web/auth.py`
- Create: `src/coding_agent/web/coordinator.py`
- Create: `src/coding_agent/web/app.py`
- Create: `src/coding_agent/web/launcher.py`
- Test: `tests/web/test_auth.py`
- Test: `tests/web/test_coordinator.py`
- Test: `tests/web/test_app.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Produces: `create_web_app(runtime: RuntimeFactory, capability: LaunchCapability) -> FastAPI`.
- Produces: `launch_web(...) -> int` that binds `127.0.0.1` on an OS-assigned port.
- Consumes only closed protocol requests and returns semantic view events.

- [ ] **Step 1: Test missing optional dependency behavior**

  Patch the lazy Web import to fail and assert exit code 2 plus the exact command
  `pip install -e ".[web]"`; assert ordinary CLI imports still work.

- [ ] **Step 2: Verify RED, then add optional dependencies and lazy `web` command**

  Add `fastapi>=0.115,<1` and `uvicorn>=0.30,<1` under `[project.optional-dependencies].web`.

- [ ] **Step 3: Write auth tests before implementation**

  Assert a capability is single-use, rotates each launch, exchanges only from an allowed Host
  and Origin, returns an HttpOnly SameSite=Strict cookie, and never appears in logs.

- [ ] **Step 4: Implement launch authentication**

  Use `secrets.token_urlsafe(32)`, constant-time comparison, a single controlling client, and
  explicit Host/Origin validation.

- [ ] **Step 5: Write coordinator tests before implementation**

  Use a fake controller to prove only one active turn, worker-thread execution, ordered event
  sequencing, cancellation, disconnect denial, and terminal result delivery.

- [ ] **Step 6: Implement coordinator and gateway routes**

  Static GET, bootstrap exchange, health, and one authenticated WebSocket are the only P0
  routes. Do not expose tool execution or arbitrary path routes.

- [ ] **Step 7: Run Task 3 and regression tests**

  Run: `python -m pytest tests/web/test_auth.py tests/web/test_coordinator.py tests/web/test_app.py tests/test_cli.py -q`

- [ ] **Step 8: Commit**

  `git commit -m "feat(web): add secure local gateway"`

### Task 4: Build the responsive application shell

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/src/main.tsx`
- Create: `web/src/app/App.tsx`
- Create: `web/src/app/theme.css`
- Create: `web/src/components/SessionRail.tsx`
- Create: `web/src/components/WorkspaceHeader.tsx`
- Create: `web/src/components/ContextDrawer.tsx`
- Create: `web/src/components/Composer.tsx`
- Create: `web/src/test/setup.ts`
- Create: `web/src/app/App.test.tsx`

**Interfaces:**
- Produces: responsive three-zone shell and CSS design tokens.
- Consumes: a transport-independent view store; no component imports WebSocket or Tauri APIs.

- [ ] **Step 1: Scaffold Vite React TypeScript and testing configuration**

  Pin React, TypeScript, Vite, Vitest, Testing Library, Zustand, Radix, and frontend rendering
  dependencies in `package.json`.

- [ ] **Step 2: Write failing shell tests**

  Assert Chinese labels, product branding injection, session rail, workspace header, collapsed
  drawer, composer controls, busy-state disablement, and accessible names.

- [ ] **Step 3: Run Vitest and verify RED**

  Run: `npm test -- --run src/app/App.test.tsx`

- [ ] **Step 4: Implement the shell and visual tokens**

  Use fluid CSS grid columns `minmax(220px, 248px) minmax(0, 1fr) auto`; avoid fixed center
  widths. Bundle Noto Sans SC and JetBrains Mono assets and declare local-only font faces.

- [ ] **Step 5: Add narrow-window behavior**

  Below 1180px, collapse the right drawer into an overlay; below 900px, collapse the session
  rail behind a button while retaining the 1024x700 acceptance layout.

- [ ] **Step 6: Run tests and production build**

  Run: `npm test -- --run`

  Run: `npm run build`

- [ ] **Step 7: Commit**

  `git commit -m "feat(web): add responsive application shell"`

### Task 5: Stream a compact, readable Agent timeline

**Files:**
- Create: `web/src/protocol/types.ts`
- Create: `web/src/protocol/transport.ts`
- Create: `web/src/protocol/websocketTransport.ts`
- Create: `web/src/state/store.ts`
- Create: `web/src/components/Timeline.tsx`
- Create: `web/src/components/ActivityRow.tsx`
- Create: `web/src/components/MarkdownMessage.tsx`
- Create: `web/src/components/ValidationCard.tsx`
- Test: `web/src/state/store.test.ts`
- Test: `web/src/components/Timeline.test.tsx`

**Interfaces:**
- Produces: `Transport` with `connect`, `request`, `subscribe`, and `close` methods.
- Produces: timeline reducer keyed by semantic event sequence and stable activity ID.

- [ ] **Step 1: Write failing reducer tests**

  Assert ordered deltas, duplicate-sequence rejection, tool upsert, activity grouping, plan
  replacement, context usage, turn completion, reconnect snapshot, and no duplicate final text.

- [ ] **Step 2: Implement transport-independent store and types**

  Validate inbound frames before store mutation. Keep the event log as authority and derive
  view state with selectors.

- [ ] **Step 3: Write failing timeline component tests**

  Assert user task surface, compact read/search row, expanded final Markdown, error and
  validation separation, external-link confirmation, disabled remote images, and Stop state.

- [ ] **Step 4: Implement timeline and safe Markdown renderer**

  Buffer active text for roughly 50ms, disable raw HTML, sanitize URLs, and lazy-load Shiki
  only after a code fence closes.

- [ ] **Step 5: Run frontend tests and build**

  Run: `npm test -- --run`

  Run: `npm run build`

- [ ] **Step 6: Commit**

  `git commit -m "feat(web): stream compact agent timeline"`

### Task 6: Add sessions, inline approvals, safe preview, and diff

**Files:**
- Create: `src/coding_agent/web/preview.py`
- Test: `tests/web/test_preview.py`
- Modify: `src/coding_agent/web/app.py`
- Create: `web/src/components/ApprovalCard.tsx`
- Create: `web/src/components/ChangesSummary.tsx`
- Create: `web/src/components/DiffViewer.tsx`
- Create: `web/src/components/FilePreview.tsx`
- Modify: `web/src/components/SessionRail.tsx`
- Test: `web/src/components/ApprovalCard.test.tsx`
- Test: `web/src/components/DiffViewer.test.tsx`
- Test: `web/src/components/SessionRail.test.tsx`

**Interfaces:**
- Produces: safe preview response containing relative path, language, size, and text.
- Consumes: SessionStore list/replay and ApprovalBroker IDs, never raw callback references.

- [ ] **Step 1: Write failing safe-preview tests**

  Reject absolute paths, traversal, escaping symlinks/junctions, binary files, invalid UTF-8,
  and content over 2 MiB; accept bounded workspace text.

- [ ] **Step 2: Implement preview through WorkspacePaths**

  Return stable error codes suitable for inline recoverable-error cards.

- [ ] **Step 3: Write failing approval, session, and diff component tests**

  Cover all three approval decisions, disabled double-submit, current-workspace session filter,
  busy switching lock, additions/deletions, long-line scroll, and empty changes.

- [ ] **Step 4: Implement the components and gateway handlers**

  Keep approval inline; open file and unified diff in the contextual right drawer; do not add
  edit, apply, undo, commit, or push controls.

- [ ] **Step 5: Test Python and frontend integration**

  Run: `python -m pytest tests/web -q`

  Run: `npm test -- --run`

- [ ] **Step 6: Commit**

  `git commit -m "feat(web): add approvals sessions and diff review"`

### Task 7: Package, document, and verify the two-minute delivery

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/demo-script.md`
- Create: `tests/web/test_static_assets.py`
- Create: `web/e2e/demo.spec.ts`
- Create: `web/playwright.config.ts`

**Interfaces:**
- Produces: wheel containing versioned Web assets and documented `coding-agent web` entry.

- [ ] **Step 1: Add a failing wheel/static asset test**

  Build a wheel, inspect its archive, and assert `coding_agent/web/static/index.html` and hashed
  JS/CSS assets are present while source maps, Node modules, test files, and credentials are
  absent.

- [ ] **Step 2: Configure Vite output and Hatch inclusion**

  Build directly into `src/coding_agent/web/static` and include only production assets.

- [ ] **Step 3: Add Playwright demo-path tests**

  At 1024x700 and 1920x1080, cover new session, send, streaming, approval, completion, changes
  summary, diff drawer, Stop, keyboard navigation, and no horizontal page overflow.

- [ ] **Step 4: Update user and architecture documentation**

  Document optional installation, loopback security, browser behavior, exact demo steps, and
  the fact that CLI/TUI and Web share the same controller and safety boundary.

- [ ] **Step 5: Run complete verification**

  Run: `python -m ruff check .`

  Run: `python -m ruff format --check .`

  Run: `python -m mypy`

  Run: `python -m pytest -q --cov=coding_agent --cov-branch --cov-report=json`

  Run: `python scripts/check_coverage.py coverage.json`

  Run: `npm test -- --run`

  Run: `npm run build`

  Run: `npx playwright test`

  Run: `python -m build`

- [ ] **Step 6: Commit**

  `git commit -m "docs(web): verify graphical frontend delivery"`

