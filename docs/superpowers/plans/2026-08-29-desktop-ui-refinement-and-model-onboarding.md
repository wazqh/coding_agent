# Desktop UI Refinement and Model Onboarding Implementation Plan

> **Status (2026-08-30):** Implemented and integrated. Retained as an engineering record; see
> `docs/roadmap.md` for the current remaining work.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a project-organized Electron interface with reliable composer completion, richer execution receipts, and secure one-screen OpenAI-compatible provider onboarding.

**Architecture:** Keep the renderer untrusted and the Python runtime local. Project/session projections and provider metadata remain Python-owned; API keys cross only a closed preload IPC boundary and are encrypted by the Electron main process before disk storage, then injected into the gateway child's environment. UI presentation consumes semantic events and never infers or exposes hidden reasoning.

**Tech Stack:** Python 3.11/3.12, Pydantic, FastAPI WebSocket protocol, Electron 44, React 19, TypeScript, Zustand, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-desktop-ui-refinement-and-model-onboarding-design.md`

## Global Constraints

- Preserve the local framework-free model/tool loop and all approval/workspace boundaries.
- Never put API keys in `models.toml`, the renderer state, WebSocket events, JSONL sessions, logs, Memory, or Skills.
- Reject Electron `safeStorage` plaintext fallback on Linux; use process-only credentials when encryption is unavailable.
- Keep model and project mutations unavailable while a turn is busy.
- Use product branding from `coding_agent.branding` and support Windows/Linux on Python 3.11/3.12.

---

### Task 1: Reliable composer completion

**Files:**
- Modify: `web/src/components/Composer.tsx`
- Modify: `web/src/app/theme.css`
- Test: `web/src/components/Composer.test.tsx`

**Interfaces:**
- Consumes: `CompletionState` from `web/src/state/store.ts`.
- Produces: keyboard selection that calls the existing `onCompletionQuery` and `onSend` callbacks without changing protocol types.

- [ ] Write a failing component test that renders more completion items than fit in the popup, presses ArrowDown, and asserts that the selected option calls `scrollIntoView`; add assertions for Tab, Enter, and Escape.
- [ ] Run `npm test -- Composer.test.tsx` and confirm the new scrolling assertion fails because selected options are not referenced or scrolled.
- [ ] Add option refs, clamp/reset selection when result sets change, keep textarea focus, and scroll the selected option with `{ block: "nearest" }`.
- [ ] Make the popup opaque and verify the focused/selected styles for `/`, `@`, and `$` share one path.
- [ ] Run `npm test -- Composer.test.tsx` and confirm the completion tests pass.

### Task 2: Project-organized session navigation

**Files:**
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `web/src/state/store.ts`
- Modify: `web/src/components/SessionRail.tsx`
- Modify: `web/src/app/theme.css`
- Test: `tests/web/test_coordinator.py`
- Test: `web/src/components/SessionRail.test.tsx`

**Interfaces:**
- Consumes: `SessionStore.list()` entries containing `workspace`, `title`, `model`, and `updated_at`.
- Produces: snapshot field `projects: [{ name, path, sessions }]` and renderer `ProjectSummary`.

- [ ] Write failing Python and React tests for two workspaces grouped as projects, the current project expanded, other projects collapsed, and session rows without repeated model labels.
- [ ] Run the two focused suites and confirm project grouping/rendering is absent.
- [ ] Add a secret-free project projection to coordinator snapshots while preserving the existing current-workspace `sessions` field for compatibility.
- [ ] Normalize project snapshots in Zustand and render the rail as an accessible project/session tree with a divider-mounted collapse control.
- [ ] Remove repeated model labels, project counts, and footer boilerplate; retain search across project and session names.
- [ ] Run the focused Python and React tests and confirm they pass.

### Task 3: Truthful inspector and execution narrative

**Files:**
- Modify: `src/coding_agent/web/presenter.py`
- Modify: `web/src/components/WorkspaceHeader.tsx`
- Modify: `web/src/components/ActivityRow.tsx`
- Modify: `web/src/components/PlanBlock.tsx`
- Modify: `web/src/components/Timeline.tsx`
- Modify: `web/src/app/theme.css`
- Test: `tests/web/test_presenter.py`
- Test: `web/src/app/App.test.tsx`
- Test: `web/src/components/Timeline.test.tsx`

**Interfaces:**
- Consumes: semantic `AgentEvent` records and existing inspector tabs.
- Produces: concise `activity.upsert` events with no duplicate `update_plan` receipt and a “任务检查器” entry point.

- [ ] Write failing presenter tests proving `update_plan` emits no activity row while plan events still emit `plan.updated`; add component tests for task inspector naming and current-step plan emphasis.
- [ ] Run focused tests and confirm duplicate plan activity and old “文件变更” naming remain.
- [ ] Filter `update_plan` tool calls/results from activity receipts, enrich command/validation/file-operation titles and summaries, and keep raw detail expandable.
- [ ] Rename the header action to “任务检查器”, make it open the last inspector tab, and show a change-count badge inside the inspector rather than making changes the global action.
- [ ] Refine plan/activity/validation styles to form one readable execution narrative; never collapse final assistant output.
- [ ] Run focused presenter and React tests and confirm they pass.

### Task 4: Python provider profile writer

**Files:**
- Create: `src/coding_agent/model_profiles.py`
- Modify: `src/coding_agent/runtime_management.py`
- Modify: `src/coding_agent/web/protocol.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `src/coding_agent/web/app.py`
- Test: `tests/test_model_profiles.py`
- Test: `tests/web/test_protocol.py`

**Interfaces:**
- Produces: `upsert_provider_profile(path, provider, base_url, model, api_key_env, compatibility) -> CatalogConfig` and request `model.provider.upsert` containing metadata only.
- Consumes: validated provider metadata; never consumes an API key.

- [ ] Write failing tests for valid atomic TOML output, replacement of an existing provider, provider/model validation, and absence of secret-like fields.
- [ ] Run focused pytest tests and confirm the writer/request do not exist.
- [ ] Implement deterministic TOML serialization using `atomic_write_text`, Pydantic validation, and generated environment names `FORGE_PROVIDER_<NORMALIZED>_API_KEY`.
- [ ] Add the metadata-only protocol request and idle coordinator/runtime management method; reload the model catalog after writing.
- [ ] Run focused pytest tests and confirm profile writes and protocol validation pass.

### Task 5: Electron encrypted credential store and gateway injection

**Files:**
- Create: `web/electron/credentialStore.ts`
- Modify: `web/electron/types.ts`
- Modify: `web/electron/preload.ts`
- Modify: `web/electron/main.ts`
- Modify: `web/electron/gatewayProcess.ts`
- Test: `web/electron/credentialStore.test.ts`
- Test: `web/electron/gatewayProcess.test.ts`

**Interfaces:**
- Produces: preload methods `saveProviderCredential(input)` and `credentialCapabilities()`; gateway start option `environment: Record<string, string>`.
- Consumes: renderer `{ provider, apiKey, apiKeyEnv }` once; returns only `{ persisted, backend }`.

- [ ] Write failing Vitest tests for encrypted save/load, Linux `basic_text` rejection, process-only fallback, payload validation, and child environment injection with no key in command arguments.
- [ ] Run Electron-focused tests and confirm the store and environment option are missing.
- [ ] Implement an injected `CredentialStore` around asynchronous Electron `safeStorage`, store encrypted bytes under Electron `userData`, and retain only process memory when secure persistence is unavailable.
- [ ] Expose a closed preload IPC API that validates provider/environment identifiers and never provides a read-secret method to the renderer.
- [ ] Load decrypted provider credentials before starting the gateway and pass them only in the spawn `env` object; keep stdout/stderr secret-free.
- [ ] Run Electron-focused tests and confirm encryption/fallback/injection behavior passes.

### Task 6: Model onboarding UI and controlled restart

**Files:**
- Create: `web/src/components/ModelManager.tsx`
- Modify: `web/src/components/ContextDrawer.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/state/store.ts`
- Modify: `web/src/app/theme.css`
- Test: `web/src/components/ModelManager.test.tsx`
- Test: `web/src/app/App.transport.test.tsx`

**Interfaces:**
- Consumes: `window.forgeDesktop.saveProviderCredential`, metadata-only `model.provider.upsert`, and existing `model.select`.
- Produces: `/model` one-screen provider select/add workflow with masked API key input and actionable secure-storage feedback.

- [ ] Write failing UI tests for opening `/model`, adding provider metadata plus a credential, masking/clearing the key, disabled busy state, and unavailable secure persistence copy.
- [ ] Run focused tests and confirm the form and bridge call are absent.
- [ ] Implement the compact model manager with provider name, base URL, model, compatibility, and password input; submit credential via preload first and metadata via WebSocket second.
- [ ] Restart or reconnect the idle gateway through the desktop main process after successful onboarding, then select the provider/model and refresh runtime state.
- [ ] Ensure API key values are cleared from React state immediately after submission and never placed in events or feedback strings.
- [ ] Run focused UI/transport tests and confirm the workflow passes.

### Task 7: Build and integrated verification

**Files:**
- Modify: `README.md`
- Modify: generated `src/coding_agent/web/static/` assets through `npm run build`

**Interfaces:**
- Consumes: all prior task interfaces.
- Produces: one launchable Electron desktop build and documented model onboarding behavior.

- [ ] Update README desktop commands and explain encrypted credential behavior and Linux process-only fallback without documenting any real secret values.
- [ ] Run `npm run typecheck`, `npm test`, `npm run build`, `npm run desktop:build`, and Electron-focused tests.
- [ ] Run `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy`, and the full pytest suite.
- [ ] Launch the Electron app against an isolated test workspace, verify project navigation/completion/inspector/model onboarding visually, and confirm no key appears in logs, WebSocket events, session JSONL, or Memory.
- [ ] Review `git status` and exclude node_modules, Electron output, temporary workspaces, sessions, credentials, and evaluation artifacts before handoff.
