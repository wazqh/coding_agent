# Shared Provider Credentials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Share provider credentials securely across Electron, TUI, and one-shot CLI; stabilize desktop workspace launch; and clarify adjacent GUI turn boundaries.

**Architecture:** Python owns an injectable credential service backed by the operating-system keyring, while named environment variables remain explicit overrides. Electron writes and migrates credentials through a stdin-only Python helper, and every runtime resolves the same credential reference. Desktop workspace selection accepts a stable environment override, and the React timeline adds a semantic new-turn boundary.

**Tech Stack:** Python 3.11/3.12, keyring, Typer, prompt-toolkit, Electron 44, React 19, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-shared-provider-credentials-design.md`

## Global Constraints

- Never put API keys in `models.toml`, renderer state, WebSocket events, JSONL sessions, logs, Memory, Skills, command arguments, or test output.
- Resolution order is named environment variable, then system credential store, then actionable failure.
- Reject null/plaintext keyring backends; unavailable storage may be process-only but never a plaintext file fallback.
- Preserve Python 3.11/3.12, Windows/Linux, TUI scrollback, project trust, approvals, and Gemini thought signatures.
- Use in-memory credential adapters in tests; CI must never access a developer's real operating-system credential store.

---

### Task 1: Stable desktop launch and adjacent-turn spacing

**Files:**
- Modify: `web/electron/main.ts`
- Modify: `web/electron/gatewayProcess.test.ts`
- Modify: `web/src/components/Timeline.tsx`
- Modify: `web/src/components/Timeline.test.tsx`
- Modify: `web/src/app/theme.css`
- Modify: `README.md`

**Interfaces:**
- Consumes: Electron `process.argv`, `process.env`, and existing timeline item ordering.
- Produces: `resolveConfiguredWorkspace(argv, environment, processCwd): string` and a `.starts-new-turn` presentation state.

- [ ] **Step 1: Write failing Electron and Timeline tests**

```ts
expect(resolveConfiguredWorkspace([], { FORGE_WORKSPACE: "D:/repo" }, "D:/web"))
  .toBe(path.resolve("D:/repo"));
expect(container.querySelectorAll(".starts-new-turn")).toHaveLength(1);
```

- [ ] **Step 2: Run tests and verify RED**

Run: `npm test -- electron/gatewayProcess.test.ts src/components/Timeline.test.tsx`
Expected: FAIL because the resolver/export and new-turn class do not exist.

- [ ] **Step 3: Implement precedence and semantic turn boundary**

```ts
export function resolveConfiguredWorkspace(
  argv: readonly string[],
  environment: Readonly<Record<string, string | undefined>>,
  processCwd: string,
): string {
  return path.resolve(commandLineValue(argv, "--cwd") ?? environment.FORGE_WORKSPACE ?? processCwd);
}
```

Mark a user item as `starts-new-turn` only when a completion item precedes it. Add responsive block
spacing and a subtle token-colored rule in CSS. Update README to use `FORGE_WORKSPACE` plus
`npm run desktop:dev`, with direct `electron.cmd` invocation as diagnostics.

- [ ] **Step 4: Run focused tests and builds**

Run: `npm test -- electron/gatewayProcess.test.ts src/components/Timeline.test.tsx`
Expected: PASS.

Run: `npm run desktop:build`
Expected: PASS.

- [ ] **Step 5: Commit**

```text
git add README.md web/electron/main.ts web/electron/gatewayProcess.test.ts web/src/components/Timeline.tsx web/src/components/Timeline.test.tsx web/src/app/theme.css
git commit -m "fix(desktop): stabilize launch and turn spacing"
```

### Task 2: Python credential service

**Files:**
- Create: `src/coding_agent/credentials.py`
- Create: `tests/test_credentials.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `CredentialService` protocol; `KeyringCredentialService`; `MemoryCredentialService`; `provider_credential_ref(provider: str) -> str`; `CredentialUnavailableError`.
- Consumes: keyring `get_password`, `set_password`, `delete_password`, and backend priority.

- [ ] **Step 1: Write failing service tests with a fake backend**

```python
def test_service_round_trips_provider_secret_without_exposing_it() -> None:
    backend = FakeKeyring()
    service = KeyringCredentialService(backend=backend)
    service.set("provider:gemini", "secret")
    assert service.get("provider:gemini") == "secret"
    assert "secret" not in repr(service)
```

Also assert invalid references, null/zero-priority backends, delete-missing behavior, and secret-free
exceptions.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest -q tests/test_credentials.py`
Expected: FAIL because `coding_agent.credentials` does not exist.

- [ ] **Step 3: Implement the minimal adapter**

```python
class CredentialService(Protocol):
    def get(self, reference: str) -> str | None:
        raise NotImplementedError
    def set(self, reference: str, secret: str) -> None:
        raise NotImplementedError
    def delete(self, reference: str) -> bool:
        raise NotImplementedError
    def available(self) -> bool:
        raise NotImplementedError
```

Use service name `forge-coding-agent`, validate `provider:<slug>`, reject non-recommended backends,
and add `keyring>=25,<27` to project dependencies.

- [ ] **Step 4: Run tests and static checks**

Run: `python -m pytest -q tests/test_credentials.py`
Expected: PASS.

Run: `python -m mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```text
git add pyproject.toml src/coding_agent/credentials.py tests/test_credentials.py
git commit -m "feat(credentials): add operating-system credential service"
```

### Task 3: Catalog and runtime credential resolution

**Files:**
- Modify: `src/coding_agent/model_catalog.py`
- Modify: `src/coding_agent/model_profiles.py`
- Modify: `src/coding_agent/runtime.py`
- Modify: `tests/test_model_catalog.py`
- Modify: `tests/test_model_profiles.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `CredentialService.get(reference)` from Task 2.
- Produces: `ProviderProfile.credential_ref: str | None`; `ModelCatalog.resolve(provider: str, model: str | None = None, *, credentials: CredentialService | None = None) -> ModelSelection`; backward-compatible inferred references.

- [ ] **Step 1: Write failing priority and compatibility tests**

```python
selected = catalog.resolve("gemini", credentials=MemoryCredentialService({"provider:gemini": "stored"}))
assert selected.api_key == "stored"
```

Add cases proving environment override wins, legacy profiles infer the provider reference, and
missing credentials name the provider without secret values.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest -q tests/test_model_catalog.py tests/test_model_profiles.py tests/test_runtime.py`
Expected: FAIL on the unsupported credential service/reference.

- [ ] **Step 3: Implement resolution and RuntimeFactory injection**

Add an optional credential service constructor argument for tests; production constructs
`KeyringCredentialService`. Keep the legacy `OPENAI_API_KEY` flow unchanged when the catalog is
empty.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest -q tests/test_model_catalog.py tests/test_model_profiles.py tests/test_runtime.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```text
git add src/coding_agent/model_catalog.py src/coding_agent/model_profiles.py src/coding_agent/runtime.py tests/test_model_catalog.py tests/test_model_profiles.py tests/test_runtime.py
git commit -m "feat(models): resolve provider credentials from shared storage"
```

### Task 4: Secret-safe CLI and TUI onboarding

**Files:**
- Modify: `src/coding_agent/cli.py`
- Modify: `src/coding_agent/runtime_management.py`
- Modify: `src/coding_agent/ui/commands.py`
- Modify: `src/coding_agent/ui/prompt.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_runtime_management.py`
- Modify: `tests/test_ui_extended.py`

**Interfaces:**
- Consumes: shared `CredentialService` and `ModelProfileWriter`.
- Produces: `ensure_active_provider_credential(catalog, state, credentials, read_secret, interactive) -> bool`; masked provider preflight and `/model add` flow; no secret-bearing command argument.

- [ ] **Step 1: Write failing CLI, management, and prompt-history tests**

```python
def test_interactive_preflight_stores_missing_provider_key_without_echo(catalog, state) -> None:
    credentials = MemoryCredentialService()
    prompted: list[bool] = []
    result = ensure_active_provider_credential(
        catalog,
        state,
        credentials,
        read_secret=lambda: prompted.append(True) or "secret",
        interactive=True,
    )
    assert result is True
    assert prompted == [True]
    assert credentials.get("provider:gemini") == "secret"

def test_model_add_never_appends_secret_to_prompt_history(ui, history_file) -> None:
    ui.configure_provider_for_test(provider="gemini", api_key="secret")
    assert "secret" not in history_file.read_text(encoding="utf-8")
```

Assert non-interactive startup returns code 2 with an actionable setup command and no secret.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest -q tests/test_cli.py tests/test_runtime_management.py tests/test_ui_extended.py`
Expected: FAIL because no shared credential setup path exists.

- [ ] **Step 3: Implement masked onboarding**

Use `prompt_toolkit.shortcuts.prompt("API Key: ", is_password=True)` before RuntimeFactory creation when an
interactive active provider lacks credentials. Extend `/model` help and management to update model
metadata and store the credential transactionally.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest -q tests/test_cli.py tests/test_runtime_management.py tests/test_ui_extended.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```text
git add src/coding_agent/cli.py src/coding_agent/runtime_management.py src/coding_agent/ui/commands.py src/coding_agent/ui/prompt.py tests/test_cli.py tests/test_runtime_management.py tests/test_ui_extended.py
git commit -m "feat(tui): configure shared provider credentials"
```

### Task 5: Electron helper and safeStorage migration

**Files:**
- Create: `src/coding_agent/credential_helper.py`
- Create: `tests/test_credential_helper.py`
- Create: `web/electron/pythonCredentialStore.ts`
- Create: `web/electron/pythonCredentialStore.test.ts`
- Modify: `web/electron/credentialStore.ts`
- Modify: `web/electron/credentialStore.test.ts`
- Modify: `web/electron/main.ts`
- Modify: `web/electron/credentialTransactions.ts`
- Modify: `web/electron/gatewayProcess.ts`

**Interfaces:**
- Consumes: Python `CredentialService`; legacy Electron `CredentialStore`; `FORGE_PYTHON`.
- Produces: `PythonCredentialStore.stage(provider, secret)` and idempotent `migrateLegacyCredentials()`.

- [ ] **Step 1: Write failing Python helper and Electron migration tests**

```ts
await migrateLegacyCredentials({ legacy, shared });
expect(await shared.has("gemini")).toBe(true);
expect(await legacy.has("FORGE_PROVIDER_GEMINI_API_KEY")).toBe(false);
```

Cover stdin transport, bounded input, metadata-only stdout, preserve-existing, failed verification,
and rollback.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest -q tests/test_credential_helper.py`
Expected: FAIL because the helper does not exist.

Run: `npm test -- electron/pythonCredentialStore.test.ts electron/credentialStore.test.ts`
Expected: FAIL because the Python bridge/migration does not exist.

- [ ] **Step 3: Implement helper, transaction, and migration**

Spawn the Python helper with fixed arguments, write the secret only to stdin, cap payload length,
and parse a fixed result schema. Keep the legacy encrypted entry until shared-store readback succeeds;
never overwrite an existing shared credential.

- [ ] **Step 4: Run focused integration tests**

Run: `python -m pytest -q tests/test_credential_helper.py tests/web`
Expected: PASS.

Run: `npm test -- electron/pythonCredentialStore.test.ts electron/credentialStore.test.ts electron/credentialTransactions.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```text
git add src/coding_agent/credential_helper.py tests/test_credential_helper.py web/electron
git commit -m "feat(desktop): migrate credentials to shared system storage"
```

### Task 6: Documentation and release verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/superpowers/specs/2026-08-30-shared-provider-credentials-design.md`
- Modify: `docs/superpowers/plans/2026-08-30-shared-provider-credentials.md`

**Interfaces:**
- Consumes: completed behavior from Tasks 1–5.
- Produces: exact launch, migration, environment override, recovery, and security documentation.

- [ ] **Step 1: Update documentation and mark delivered status**

Document PowerShell and POSIX launch commands, the credential resolution order, one-time migration,
Keyring-unavailable behavior, key rotation, and deletion without printing secrets.

- [ ] **Step 2: Run complete verification**

Run: `python -m ruff check .`
Run: `python -m ruff format --check .`
Run: `python -m mypy`
Run: `python -m pytest -q --cov=coding_agent --cov-branch --cov-report=json:coverage.json`
Run: `python scripts/check_coverage.py coverage.json`
Run: `python -m bandit -q -r src`
Run: `python -m build --no-isolation`
Run: `npm test` from `web/`
Run: `npm run build` from `web/`
Run: `npm run desktop:build` from `web/`
Run: `npm run test:e2e` from `web/`

Expected: every command passes; generated renderer assets match their source; no secret appears in
Git diff, logs, sessions, or fixtures.

- [ ] **Step 3: Commit**

```text
git add README.md docs pyproject.toml
git commit -m "docs(credentials): document shared provider setup"
```
