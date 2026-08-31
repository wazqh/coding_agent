# Forge Coding Agent Electron Desktop V2 Implementation Plan

> **Status (2026-08-30):** Implemented and integrated. This file is retained as an engineering
> record; unchecked wording does not supersede the current delivery status in `docs/roadmap.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a secure Electron + React desktop frontend that reuses the Python Agent runtime,
matches every interactive TUI capability, and delivers a polished task/review workflow for video
demonstration and direct comparison with Web V1.

**Architecture:** Electron main supervises the existing loopback Python gateway and exposes only a
minimal preload bridge. The Python gateway gains frontend-neutral management services and a
versioned semantic protocol; the renderer maps them into a three-column task cockpit, management
surfaces, and composer completions. Model/tool/session authority remains in Python.

**Tech Stack:** Python 3.11/3.12, FastAPI, Pydantic, React 19, TypeScript 5.9, Zustand, Electron,
Vite, Vitest, Testing Library, Playwright Electron, Noto Sans SC, JetBrains Mono.

**Spec:** `docs/superpowers/specs/2026-08-29-electron-desktop-v2-design.md`

## Global Constraints

- Product name comes from `coding_agent.branding`; executable/module/distribution names stay
  `coding-agent`, `coding_agent`, and `forge-coding-agent`.
- Support Python 3.11/3.12 and Electron development on Windows and Linux.
- Preserve CLI/TUI behavior and ordinary terminal scrollback.
- Do not introduce an Agent framework, Agent SDK, multi-agent execution, embedded editor, terminal
  emulator, installer, updater, Git push/PR, automatic undo, or hidden reasoning display.
- Renderer has no generic file, shell, environment, credential, or arbitrary IPC authority.
- Workspace paths, approvals, trust, secrets, Gemini thought signatures, session restoration, and
  compaction keep their existing safety invariants.
- Add regression tests for every behavior change; all hand edits use `apply_patch`.
- V1 stays on `feat/web-ui`; all V2 work stays in `feat/electron-ui-v2` until the user authorizes a
  merge or push.
- Interaction references are principles, not copied UI: Codex exposes developer detail, review
  views, progress above the composer, `/plan`, and `@file`; Claude Desktop places project/model/
  permissions near the prompt, supports interrupt/steer, and provides visual diff review.

## File Structure

### Electron process boundary

- `web/electron/main.ts`: Electron application lifecycle and BrowserWindow construction only.
- `web/electron/preload.ts`: narrow `contextBridge` API and no generic IPC forwarding.
- `web/electron/gatewayProcess.ts`: Python executable selection, argument construction, startup
  handshake parsing, timeout, and child cleanup.
- `web/electron/windowPolicy.ts`: navigation, permission, external-link, and window-open policy.
- `web/electron/types.ts`: preload and gateway lifecycle types shared by main/preload tests.
- `web/electron/*.test.ts`: pure unit tests for the Electron boundary.
- `web/tsconfig.electron.json`: strict Electron main/preload compilation.

### Python desktop services

- `src/coding_agent/web/handshake.py`: one-line desktop startup handshake serializer/parser contract.
- `src/coding_agent/runtime_management.py`: frontend-neutral status, permissions, steps, model,
  Memory, Skills, Context, Plan, and raw-display commands.
- `src/coding_agent/web/protocol.py`: protocol V2 closed request and event models.
- `src/coding_agent/web/coordinator.py`: busy-state guard and semantic management event publication.
- `src/coding_agent/web/app.py`: validated request dispatch only.
- `src/coding_agent/web/launcher.py`: optional machine-readable handshake without logging capability.
- `tests/test_runtime_management.py`: direct shared-service tests.
- `tests/web/test_handshake.py`, `tests/web/test_protocol.py`, `tests/web/test_app.py`: gateway boundary tests.

### React renderer

- `web/src/state/managementStore.ts`: normalized management state and request lifecycle.
- `web/src/commands/catalog.ts`: desktop command definitions sourced from protocol data.
- `web/src/commands/parser.ts`: slash command to semantic request mapping.
- `web/src/completion/completionModel.ts`: `/`, `$`, and `@` completion state and keyboard behavior.
- `web/src/components/ManagementCenter.tsx`: common drawer shell and navigation.
- `web/src/components/management/*.tsx`: focused Model, Permissions, Steps, Memory, Skills, Context,
  Status, and Help panels.
- `web/src/components/CommandPalette.tsx`: anchored full-width completion list.
- `web/src/components/TurnHeader.tsx`, `TurnEvidence.tsx`, `ActivityGroup.tsx`: task hierarchy and audit.
- `web/src/components/Inspector.tsx`: Changes, Run, and Context tabs.
- `web/src/components/AppChrome.tsx`: Electron title bar and responsive rail/inspector layout.
- `web/src/app/theme.css`: tokenized light/dark visual system and responsive geometry.

---

### Task 1: Secure Electron shell and Python gateway supervision

**Files:**
- Create: `web/electron/types.ts`
- Create: `web/electron/gatewayProcess.ts`
- Create: `web/electron/windowPolicy.ts`
- Create: `web/electron/preload.ts`
- Create: `web/electron/main.ts`
- Create: `web/electron/gatewayProcess.test.ts`
- Create: `web/electron/windowPolicy.test.ts`
- Create: `web/tsconfig.electron.json`
- Create: `src/coding_agent/web/handshake.py`
- Create: `tests/web/test_handshake.py`
- Modify: `src/coding_agent/web/launcher.py`
- Modify: `src/coding_agent/cli.py`
- Modify: `tests/web/test_launcher.py`
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

**Interfaces:**
- Consumes: existing `coding-agent web --cwd PATH --no-open` gateway startup.
- Produces: `GatewayProcess.start(options): Promise<GatewayReady>`,
  `GatewayProcess.stop(): Promise<void>`, `installWindowPolicy(window): void`, and
  `window.forgeDesktop` with only readiness, workspace picker, external-link, and window actions.

- [ ] **Step 1: Write failing Python handshake and launcher tests**

```python
def test_desktop_handshake_is_single_line_and_keeps_capability_out_of_logs() -> None:
    value = DesktopHandshake(origin="http://127.0.0.1:43210", capability="secret")
    line = serialize_desktop_handshake(value)
    assert line.startswith("FORGE_DESKTOP_READY ")
    assert "secret" in line
    assert "secret" not in sanitize_launcher_log(line)


def test_launcher_emits_desktop_handshake_only_when_requested(monkeypatch) -> None:
    output: list[str] = []
    launch_web(cwd=Path("."), open_browser=False, desktop_handshake=output.append)
    assert len(output) == 1
    assert output[0].startswith("FORGE_DESKTOP_READY ")
```

- [ ] **Step 2: Run the focused Python tests and verify they fail**

Run: `python -m pytest -q tests/web/test_handshake.py tests/web/test_launcher.py`

Expected: FAIL because `DesktopHandshake` and the desktop handshake option do not exist.

- [ ] **Step 3: Implement the bounded startup handshake**

```python
@dataclass(frozen=True)
class DesktopHandshake:
    origin: str
    capability: str


def serialize_desktop_handshake(value: DesktopHandshake) -> str:
    payload = json.dumps(asdict(value), ensure_ascii=True, separators=(",", ":"))
    return f"FORGE_DESKTOP_READY {payload}"
```

Add an internal `--desktop-handshake` CLI flag used only by Electron. The normal Web command keeps
its current human-readable output. The handshake writer is injected in tests and the launcher never
writes it to application logs.

- [ ] **Step 4: Write failing Electron process and window-policy tests**

```ts
it("builds a shell-free Python argv confined to one workspace", () => {
  expect(buildGatewayCommand("python", "D:\\repo")).toEqual({
    file: "python",
    args: ["-m", "coding_agent", "web", "--cwd", "D:\\repo", "--no-open", "--desktop-handshake"],
  });
});

it("rejects navigation away from the gateway origin", () => {
  expect(isAllowedNavigation("http://127.0.0.1:43210/chat", "http://127.0.0.1:43210")).toBe(true);
  expect(isAllowedNavigation("https://example.com", "http://127.0.0.1:43210")).toBe(false);
});
```

- [ ] **Step 5: Run Electron unit tests and verify they fail**

Run: `npm test -- electron/gatewayProcess.test.ts electron/windowPolicy.test.ts`

Expected: FAIL because the Electron modules and dependency are absent.

- [ ] **Step 6: Add Electron and implement the secure shell**

Use `spawn(file, args, { shell: false, windowsHide: true })`. Parse exactly one prefixed JSON line,
validate loopback origin/capability lengths, enforce a 20-second startup timeout, and retain no
stdout containing the capability. Construct BrowserWindow with:

```ts
const webPreferences: Electron.WebPreferences = {
  preload: preloadPath,
  contextIsolation: true,
  sandbox: true,
  nodeIntegration: false,
  webSecurity: true,
};
```

Deny permission requests, `window.open`, and cross-origin navigation. Confirm external HTTP(S)
links in main before `shell.openExternal`. On close, request turn cancellation through the gateway,
wait up to two seconds, then terminate only the tracked child.

- [ ] **Step 7: Run focused checks and commit**

Run: `python -m pytest -q tests/web/test_handshake.py tests/web/test_launcher.py`

Run: `npm run typecheck && npm test -- electron/gatewayProcess.test.ts electron/windowPolicy.test.ts`

Expected: PASS.

Commit: `feat(desktop): add secure Electron runtime shell`

---

### Task 2: Frontend-neutral runtime management foundation

**Files:**
- Create: `src/coding_agent/runtime_management.py`
- Create: `tests/test_runtime_management.py`
- Modify: `src/coding_agent/web/protocol.py`
- Modify: `tests/web/test_protocol.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `tests/web/test_coordinator.py`
- Modify: `src/coding_agent/web/app.py`
- Modify: `tests/web/test_app.py`

**Interfaces:**
- Consumes: `AgentController`, `RuntimeFactory`, `WorkspaceSettingsStore`, `ModelManager`,
  `MemoryStore`, and `SkillRegistry` public methods.
- Produces: `RuntimeManagement.snapshot() -> RuntimeSnapshot`,
  `set_permissions(mode)`, `set_steps(value)`, `reset_steps()`, and coordinator methods that reject
  mutations while busy and emit sanitized semantic results.

- [ ] **Step 1: Write failing snapshot and busy-state tests**

```python
def test_runtime_snapshot_reports_tui_status_without_secrets(runtime_management) -> None:
    snapshot = runtime_management.snapshot()
    assert snapshot.model.id == "gemini-flash"
    assert snapshot.permissions == "prompt"
    assert snapshot.steps.minimum == 30
    assert snapshot.context.percent_used >= 0
    assert "api_key" not in snapshot.model.model_dump_json().casefold()


def test_management_mutation_is_rejected_while_turn_is_busy(coordinator) -> None:
    coordinator._busy = True
    with pytest.raises(CoordinatorBusyError):
        coordinator.set_permissions("auto")
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest -q tests/test_runtime_management.py tests/web/test_coordinator.py`

Expected: FAIL because `RuntimeManagement` and management coordinator methods do not exist.

- [ ] **Step 3: Implement immutable management DTOs and guards**

```python
class StepSettings(BaseModel):
    current: int = Field(ge=30, le=999)
    configured_default: int = Field(ge=30, le=999)
    overridden: bool


class RuntimeSnapshot(BaseModel):
    workspace: str
    session_id: str
    lifecycle: LifecycleState
    permissions: Literal["prompt", "auto", "read-only"]
    steps: StepSettings
    model: ModelSummary
    context: ContextSummary
    resources: ResourceSummary
```

`RuntimeManagement` validates commands once, mutates only through existing stores/managers, clears
approval grants when permissions change, and returns DTOs with allowlisted public fields.

- [ ] **Step 4: Write failing protocol V2 request tests**

```python
@pytest.mark.parametrize(
    "request_type",
    [
        "runtime.status",
        "steps.get",
        "steps.set",
        "steps.reset",
        "permissions.get",
        "permissions.set",
        "plan.get",
    ],
)
def test_protocol_v2_accepts_management_requests(request_type: str) -> None:
    payload = request_payload(request_type)
    assert parse_client_request(payload).type == request_type


def test_steps_set_rejects_eleven() -> None:
    with pytest.raises(ValidationError):
        parse_client_request(request_payload("steps.set", value=11))
```

- [ ] **Step 5: Implement protocol V2 and semantic command results**

Increment `PROTOCOL_VERSION` to `2`. Add discriminated request models with `extra="forbid"` and
bounded strings. Add `runtime.updated`, `command.completed`, and `completion.updated` view events.
Dispatch requests to coordinator methods; never forward slash strings to `InteractiveShell`.

- [ ] **Step 6: Verify management behavior and commit**

Run: `python -m pytest -q tests/test_runtime_management.py tests/web/test_protocol.py tests/web/test_coordinator.py tests/web/test_app.py`

Expected: PASS.

Commit: `feat(desktop): expose safe runtime management protocol`

---

### Task 3: Model catalog, project steps, and permission management

**Files:**
- Modify: `src/coding_agent/runtime_management.py`
- Modify: `tests/test_runtime_management.py`
- Modify: `src/coding_agent/web/protocol.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Create: `web/src/state/managementStore.ts`
- Create: `web/src/state/managementStore.test.ts`
- Create: `web/src/components/management/ModelPanel.tsx`
- Create: `web/src/components/management/StepsPanel.tsx`
- Create: `web/src/components/management/PermissionsPanel.tsx`
- Create: `web/src/components/management/RuntimeStatusPanel.tsx`
- Create: `web/src/components/management/ManagementPanels.test.tsx`

**Interfaces:**
- Consumes: Task 2 `RuntimeManagement` and protocol V2.
- Produces: model list/select/reload, next-turn step budget, permission switching, and normalized
  `ManagementState` used by composer and management center.

- [ ] **Step 1: Write failing Python behavior tests**

```python
def test_model_switch_persists_only_provider_and_model(runtime_management) -> None:
    result = runtime_management.select_model(provider="gemini", model_id="gemini-pro")
    assert result.provider == "gemini"
    assert result.id == "gemini-pro"
    assert "secret" not in result.model_dump_json()


def test_steps_apply_to_next_turn_and_permissions_revoke_grants(runtime_management) -> None:
    runtime_management.set_steps(40)
    runtime_management.set_permissions("read-only")
    assert runtime_management.snapshot().steps.current == 40
    assert runtime_management.controller.approval.session_grants == set()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest -q tests/test_runtime_management.py`

Expected: FAIL on missing model methods and updated DTO fields.

- [ ] **Step 3: Implement model, steps, and permission commands**

Add `model.list`, `model.select`, `model.reload`, `steps.set/reset`, and `permissions.set`. Preserve
legacy model-ID selection by resolving it against the active provider. Apply step changes only to a
new controller/next turn; return a `takes_effect="next_turn"` field. Reload reports sanitized
provider diagnostics and never key values.

- [ ] **Step 4: Write failing renderer state and panel tests**

```tsx
it("disables runtime mutations while a turn is active", () => {
  render(<StepsPanel state={busyState} send={send} />);
  expect(screen.getByRole("slider", { name: "最大步骤" })).toBeDisabled();
  expect(screen.getByText("任务运行期间不可更改")).toBeVisible();
});

it("groups models by provider and marks the active model", () => {
  render(<ModelPanel state={catalogState} send={send} />);
  expect(screen.getByRole("option", { name: /gemini-pro/ })).toHaveAttribute("aria-selected", "true");
});
```

- [ ] **Step 5: Implement normalized management state and panels**

`managementStore` tracks `idle | loading | ready | saving | error` per resource and applies
monotonic sequence updates. Panels send semantic requests, keep stale values visible during reload,
display sanitized errors inline, and expose 30-999 step presets plus a numeric field.

- [ ] **Step 6: Verify and commit**

Run: `python -m pytest -q tests/test_runtime_management.py tests/web/test_protocol.py tests/web/test_app.py`

Run: `npm test -- src/state/managementStore.test.ts src/components/management/ManagementPanels.test.tsx`

Expected: PASS.

Commit: `feat(desktop): add model steps and permission controls`

---

### Task 4: Memory, Skills, Plan, Context, raw output, and help parity

**Files:**
- Modify: `src/coding_agent/runtime_management.py`
- Modify: `tests/test_runtime_management.py`
- Modify: `src/coding_agent/web/protocol.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Create: `web/src/components/ManagementCenter.tsx`
- Create: `web/src/components/management/MemoryPanel.tsx`
- Create: `web/src/components/management/SkillsPanel.tsx`
- Create: `web/src/components/management/ContextPanel.tsx`
- Create: `web/src/components/management/PlanPanel.tsx`
- Create: `web/src/components/management/HelpPanel.tsx`
- Create: `web/src/components/management/ResourcePanels.test.tsx`
- Modify: `web/src/state/managementStore.ts`

**Interfaces:**
- Consumes: management foundation and current controller stores.
- Produces: all remaining TUI management actions plus consistent drawer navigation.

- [ ] **Step 1: Write failing Memory/Skills/Context service tests**

```python
def test_memory_clear_requires_explicit_confirmation(runtime_management) -> None:
    with pytest.raises(ManagementValidationError):
        runtime_management.clear_memory(confirm=False)


def test_skill_reload_preserves_session_disabled_names(runtime_management) -> None:
    runtime_management.set_skill_enabled("demo", False)
    runtime_management.reload_skills()
    assert runtime_management.skills_snapshot().by_name("demo").enabled is False


def test_compact_reports_before_after_without_deleting_transcript(runtime_management) -> None:
    result = runtime_management.compact_context()
    assert result.tokens_after <= result.tokens_before
    assert result.transcript_preserved is True
```

- [ ] **Step 2: Run focused Python tests and verify failure**

Run: `python -m pytest -q tests/test_runtime_management.py`

Expected: FAIL because resource-management methods are missing.

- [ ] **Step 3: Implement resource commands with existing isolation rules**

Add list/toggle/remember/forget/clear Memory methods; list/search/toggle/reload Skills methods;
Plan/status reads; Context estimate/compact; `display.raw.set`; and `display.clear`. Return source,
conflict, enabled, active, injection, and transcript-preservation metadata. Reuse existing secret
filtering and project trust checks.

- [ ] **Step 4: Write failing React resource-panel tests**

```tsx
it("requires a second action before clearing memory", async () => {
  render(<MemoryPanel state={memoryState} send={send} />);
  await user.click(screen.getByRole("button", { name: "清空 Memory" }));
  expect(screen.getByRole("dialog", { name: "确认清空 Memory" })).toBeVisible();
  expect(send).not.toHaveBeenCalled();
});

it("shows compact before and after token estimates", () => {
  render(<ContextPanel state={compactedContext} send={send} />);
  expect(screen.getByText(/18,420.*9,860/)).toBeVisible();
  expect(screen.getByText("原始 transcript 已保留")).toBeVisible();
});
```

- [ ] **Step 5: Implement the common management center and focused panels**

Use one dialog/drawer shell with roving keyboard focus, Escape close, responsive overlay behavior,
and read-only availability while busy. Keep destructive confirmation inside the relevant panel.
Help content comes from a protocol-provided command catalog so descriptions cannot drift from TUI
command definitions.

- [ ] **Step 6: Verify and commit**

Run: `python -m pytest -q tests/test_runtime_management.py tests/web/test_protocol.py tests/web/test_app.py`

Run: `npm test -- src/components/management/ResourcePanels.test.tsx`

Expected: PASS.

Commit: `feat(desktop): complete TUI management parity`

---

### Task 5: Slash, skill, and file completion with local command routing

**Files:**
- Create: `web/src/commands/catalog.ts`
- Create: `web/src/commands/parser.ts`
- Create: `web/src/commands/parser.test.ts`
- Create: `web/src/completion/completionModel.ts`
- Create: `web/src/completion/completionModel.test.ts`
- Create: `web/src/components/CommandPalette.tsx`
- Create: `web/src/components/CommandPalette.test.tsx`
- Modify: `web/src/components/Composer.tsx`
- Modify: `web/src/components/Composer.test.tsx`
- Modify: `src/coding_agent/web/protocol.py`
- Modify: `src/coding_agent/web/coordinator.py`
- Modify: `tests/web/test_protocol.py`

**Interfaces:**
- Consumes: protocol command catalog, model catalog, Skills list, and bounded workspace file index.
- Produces: `parseLocalCommand(text): LocalCommand | null`,
  `getCompletions(query, sources): CompletionItem[]`, and composer routing that never sends local
  commands to the model.

- [ ] **Step 1: Write failing parser and completion model tests**

```ts
it("maps slash commands to semantic management requests", () => {
  expect(parseLocalCommand("/steps 40")).toEqual({ type: "steps.set", value: 40 });
  expect(parseLocalCommand("/memory remember Run pytest")).toEqual({
    type: "memory.remember", text: "Run pytest",
  });
});

it("returns bounded argument-aware completions", () => {
  expect(getCompletions("/model use ge", sources)[0].insertText).toBe("/model use gemini ");
  expect(getCompletions("@prot", sources)).toHaveLength(100);
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `npm test -- src/commands/parser.test.ts src/completion/completionModel.test.ts`

Expected: FAIL because parser and completion modules are absent.

- [ ] **Step 3: Implement closed local command routing**

Represent every command as a discriminated TypeScript union matching protocol V2. Reject invalid
arguments locally with the same bounds as Pydantic. `/exit` calls the preload close method;
`/clear` changes renderer display state only; unknown slash input shows help and is not sent.

- [ ] **Step 4: Add safe completion queries**

Implement `completion.query` for `command | provider | model | step | skill | file`. File matches are
workspace-relative, skip `.git` and escaping links, cap at 100, and return only display/insert text.
The frontend debounces remote file queries and discards stale request IDs.

- [ ] **Step 5: Write failing command palette interaction tests**

```tsx
it("fills composer width and supports arrows enter and escape", async () => {
  render(<Composer {...props} />);
  await user.type(screen.getByRole("textbox"), "/h");
  const palette = screen.getByRole("listbox", { name: "命令补全" });
  expect(palette).toHaveStyle({ width: "100%" });
  await user.keyboard("{ArrowDown}{Enter}");
  expect(screen.getByRole("textbox")).toHaveValue("/help");
});
```

- [ ] **Step 6: Implement anchored palette and composer shortcuts**

Use CSS inset positioning against the composer, max-height based on available viewport, one shared
surface across command/description columns, scroll selected rows into view, and keep Enter send /
Shift+Enter newline / Escape close-or-cancel behavior deterministic.

- [ ] **Step 7: Verify and commit**

Run: `npm test -- src/commands src/completion src/components/CommandPalette.test.tsx src/components/Composer.test.tsx`

Run: `python -m pytest -q tests/web/test_protocol.py tests/web/test_coordinator.py`

Expected: PASS.

Commit: `feat(desktop): add command skill and file completion`

---

### Task 6: Codex/Claude-inspired task cockpit and audit hierarchy

**Files:**
- Create: `web/src/components/AppChrome.tsx`
- Create: `web/src/components/TurnHeader.tsx`
- Create: `web/src/components/TurnEvidence.tsx`
- Create: `web/src/components/ActivityGroup.tsx`
- Create: `web/src/components/Inspector.tsx`
- Create: `web/src/components/TaskCockpit.test.tsx`
- Modify: `web/src/components/Timeline.tsx`
- Modify: `web/src/components/ActivityRow.tsx`
- Modify: `web/src/components/ApprovalCard.tsx`
- Modify: `web/src/components/ValidationCard.tsx`
- Modify: `web/src/components/SessionRail.tsx`
- Modify: `web/src/components/Composer.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/app/theme.css`
- Modify: `web/src/state/store.ts`
- Modify: `web/src/protocol/types.ts`
- Modify: `src/coding_agent/web/presenter.py`
- Modify: `tests/web/test_presenter.py`

**Interfaces:**
- Consumes: semantic timeline, runtime snapshot, management state, changes, and approvals.
- Produces: responsive three-column layout, explicit lifecycle, grouped audit rows, always-expanded
  final answer, persistent inspector, and evidence footer.

- [ ] **Step 1: Write failing presenter tests for audit and lifecycle data**

```python
def test_tool_audit_includes_duration_approval_and_recovery_fields(presenter) -> None:
    events = present_call_and_failure(presenter)
    activity = next(event for event in events if event.type == "activity.upsert")
    assert activity.data["duration_ms"] >= 0
    assert activity.data["approval_status"] in {"not_required", "approved", "denied"}
    assert activity.data["side_effect"] in {"none", "possible", "applied"}
    assert activity.data["recovery_action"]
```

- [ ] **Step 2: Run presenter tests and verify failure**

Run: `python -m pytest -q tests/web/test_presenter.py`

Expected: FAIL on missing audit fields.

- [ ] **Step 3: Extend presenter with observable facts only**

Track call start time by call ID, approval resolution, normalized targets, bounded argument/result
summaries, exit/timeout/truncation, and side-effect certainty. Add lifecycle transitions
`idle/requesting/awaiting_approval/executing_tool/completed/cancelled/failed`. Do not infer success
from prose and do not emit reasoning content.

- [ ] **Step 4: Write failing task-cockpit tests**

```tsx
it("keeps final output expanded after a full-width divider", () => {
  render(<TaskCockpit fixture={completedFixture} />);
  expect(screen.getByTestId("final-divider")).toHaveStyle({ width: "100%" });
  expect(screen.getByRole("article", { name: "Agent 最终回答" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "展开回答" })).not.toBeInTheDocument();
});

it("groups routine reads but keeps writes approvals and tests distinct", () => {
  render(<TaskCockpit fixture={activityFixture} />);
  expect(screen.getByText("读取 4 个文件")).toBeVisible();
  expect(screen.getByText("修改 auth.py")).toBeVisible();
  expect(screen.getByText("运行 12 项测试")).toBeVisible();
});
```

- [ ] **Step 5: Implement the three-column task cockpit**

Use CSS Grid tracks `248px minmax(0, 1fr) minmax(420px, 32vw)` on wide screens, a collapsible rail
below 1280px, and overlay inspector below 1180px. Center prose uses `max-width: 880px`; activities,
approvals, validation, and change summaries use the full center track. The final answer has no
nested scroll container.

- [ ] **Step 6: Implement activity grouping, approvals, and evidence footer**

Group consecutive completed read/list/search actions within one turn. Preserve independent writes,
commands, failures, validation, and approvals. Approval cards show full tool name, target or exact
command, cwd, risk, diff, and three decisions. Footer displays only available measured values:
validation, changes, calls, requests/retries, steps/max, context, compactions, elapsed.

- [ ] **Step 7: Apply visual tokens and responsive geometry tests**

Define color, spacing, radius, font, and elevation CSS variables. Bundle Noto Sans SC and JetBrains
Mono only. Add DOM assertions that composer/palette/inspector consume parent width and do not use
hard-coded decorative line widths. Add screenshot fixture labels for 1024x700 and 1920x1080.

- [ ] **Step 8: Verify and commit**

Run: `python -m pytest -q tests/web/test_presenter.py`

Run: `npm test -- src/components/TaskCockpit.test.tsx src/components/Timeline.test.tsx src/app/App.test.tsx`

Run: `npm run typecheck && npm run build`

Expected: PASS.

Commit: `feat(desktop): redesign task and review workspace`

---

### Task 7: Electron end-to-end, real-model validation, and comparison delivery

**Files:**
- Create: `web/e2e/electron-desktop.spec.ts`
- Create: `web/e2e/electron-real-model.spec.ts`
- Create: `web/playwright.electron.config.ts`
- Create: `docs/desktop-demo-script.md`
- Create: `docs/desktop-tui-parity.md`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `web/package.json`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: production Electron shell, production gateway, compiled renderer, and optional current
  model environment.
- Produces: repeatable mock screenshots, real-model evidence, documented launch, parity matrix, and
  CI coverage.

- [ ] **Step 1: Write the failing Electron Playwright acceptance flow**

```ts
test("desktop completes the task review loop", async () => {
  const app = await electron.launch({ args: [desktopMain, "--cwd", fixtureWorkspace] });
  const page = await app.firstWindow();
  await expect(page.getByText("Forge Coding Agent")).toBeVisible();
  await page.getByRole("textbox").fill("修复认证逻辑并运行相关测试");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByRole("button", { name: "允许一次" }).click();
  await expect(page.getByRole("article", { name: "Agent 最终回答" })).toBeVisible();
  await expect(page.getByText(/验证通过/)).toBeVisible();
  await app.close();
});
```

- [ ] **Step 2: Run Electron E2E and verify failure**

Run: `npm run test:electron:e2e`

Expected: FAIL until the build/fixture launch integration is complete.

- [ ] **Step 3: Implement deterministic mock gateway fixtures and screenshots**

Drive the actual Electron window with a mock model injected at `RuntimeFactory`, not a fake React
store. Cover new/resume session, stream, stop, three approval decisions, every management panel,
completion, diff/file preview, error recovery, and close cleanup. Capture ignored artifacts:

```text
.test-runs/visual/v1-1024x700.png
.test-runs/visual/v1-1920x1080.png
.test-runs/visual/v2-1024x700.png
.test-runs/visual/v2-1920x1080.png
```

- [ ] **Step 4: Add a path-verified real-model validation fixture**

Create `.test-runs/electron-real-model-workspace` only after resolving it inside the V2 worktree.
Populate a scoped `AGENTS.md`, a small failing test, and one source file. Check credential variables
for presence only. Exercise read, plan, approval-gated edit, approval-gated focused test, correction,
final evidence, follow-up without replay, session resume, and context. Preserve sanitized JSONL and
screenshots for manual review; report unavailable service as unavailable, never as a pass.

- [ ] **Step 5: Update docs and CI**

Document `npm ci` and `npm run desktop:dev -- --cwd .`, the Python interpreter override, V1/V2
comparison commands, security boundary, parity matrix, and two-minute demo. CI installs Electron
dependencies and runs unit/type/build checks plus offscreen Electron tests on Windows/Linux Python
3.11/3.12 without a real provider key.

- [ ] **Step 6: Run complete verification**

Run:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q --cov=coding_agent --cov-branch
python scripts/check_coverage.py coverage.json
Set-Location web
npm run typecheck
npm test
npm run build
npm run test:electron:e2e
Set-Location ..
python -m build --no-isolation
```

Expected: all required checks pass. Record any environment-only isolated-build limitation separately.

- [ ] **Step 7: Inspect artifacts, secrets, and repository state**

Run: `git status --short`

Run: `git diff --check`

Run a secret-pattern scan over tracked changes and screenshots without printing environment values.
Confirm `node_modules`, `.test-runs`, sessions, credentials, build output, and evaluation output are
ignored/untracked.

- [ ] **Step 8: Commit the verified delivery**

Commit: `test(desktop): verify Electron delivery`

Do not merge or push without later user authorization.

## Plan Self-Review

- Spec coverage: Electron lifecycle, renderer boundary, TUI parity, protocol, management, completion,
  task hierarchy, audit, responsive layout, real-model run, V1/V2 screenshots, documentation, and
  safety each map to a task above.
- Scope control: multi-agent, terminal, editor, preview server, installer, update, undo, and remote
  Git actions remain excluded.
- Type consistency: Task 1 produces `GatewayProcess`; Task 2 produces `RuntimeManagement` and
  protocol V2; Tasks 3-5 consume those types; Task 6 consumes semantic state; Task 7 consumes the
  production build.
- No placeholder steps remain; each code-changing task starts with a failing test and ends with a
  focused verification and commit.

