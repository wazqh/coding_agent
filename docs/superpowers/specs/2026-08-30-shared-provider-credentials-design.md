# Shared Provider Credentials Design

## Status

Approved in chat on 2026-08-30. This module makes provider credentials configured from Electron
available to the TUI and one-shot CLI without storing plaintext secrets in Forge configuration,
sessions, logs, Memory, Skills, command arguments, or the frontend protocol.

## Goals

- Make Electron, TUI, and non-interactive commands resolve the same provider credential.
- Keep environment variables as explicit process-local overrides for CI and temporary testing.
- Preserve `models.toml` as non-secret provider/model metadata.
- Migrate existing Electron `safeStorage` credentials without losing or exposing them.
- Replace the npm-dependent `--cwd` launch path with a stable documented workspace override.

## Credential architecture

Python owns a small `CredentialService` interface with `get`, `set`, `delete`, and availability
inspection. Its production implementation uses the operating-system credential store through
Python `keyring`; tests use an in-memory implementation. The service name is
`forge-coding-agent`, and provider entries use deterministic identifiers such as
`provider:gemini`.

Provider metadata gains a non-secret `credential_ref`. Existing profiles without this field infer
`provider:<provider-name>`, so the catalog remains backward compatible. Resolution order is:

1. the non-empty environment variable named by `api_key_env`;
2. the credential referenced by `credential_ref` in the system store;
3. a precise missing-credential error naming the provider and supported setup action.

The environment wins deliberately: CI and temporary shell overrides must never mutate stored
credentials. `OPENAI_API_KEY` remains the legacy path only when no provider catalog is active.

## TUI and CLI behavior

The interactive model-management flow accepts provider name, Base URL, model ID, compatibility,
and a masked API Key. Secret input is never added to prompt history. A non-interactive credential
command accepts a key only through masked stdin, never a command-line argument.

Because the current runtime requires a model credential before the TUI opens, CLI startup performs
a narrow provider preflight. When an active catalog profile lacks both its environment override and
stored credential, an interactive terminal offers masked credential entry; non-interactive commands
fail with an actionable error. Once the TUI is running, `/model` can add/update providers through
the same service.

## Electron behavior and migration

Electron stops treating its private `safeStorage` file as the canonical credential source. Model
onboarding sends the secret only across the existing narrow preload IPC boundary to an internal
Python credential helper over stdin. The helper returns non-secret status only. Runtime startup then
resolves the credential directly from the shared system store.

On the first upgraded launch, Electron checks each existing encrypted provider entry only when the
shared store has no corresponding credential. It decrypts in the main process, writes through the
Python helper, verifies a successful read, and only then removes the legacy entry. A failed or
unavailable migration retains the old encrypted data and reports a recoverable setup error. Existing
shared credentials are never overwritten automatically.

No plaintext file fallback is permitted. When no recommended system backend is available, GUI/TUI
may use an explicitly supplied key for the current process only and must clearly report that it was
not persisted.

## Desktop launch

Electron resolves the workspace in this order:

```text
--cwd > FORGE_WORKSPACE > process working directory
```

README uses `FORGE_WORKSPACE` with `npm run desktop:dev`, avoiding npm versions that consume
`--cwd` instead of forwarding it. Direct invocation of the local Electron binary remains the
documented diagnostic path.

## Turn boundary polish

The timeline treats one user request, its Agent activity/output, and its completion receipt as one
visual turn. When another user request follows a completion receipt, the next turn receives a
responsive top gap and a subtle boundary so the completion marker and user surface never appear as
one connected block. The treatment uses existing theme tokens, adds no fixed-width assumptions,
and remains visible without relying on animation.

## Security and failure handling

- Secrets are redacted by representation and never returned by management/status APIs.
- Credential helper input uses stdin and bounded JSON; stdout contains metadata only.
- Backend unavailable, locked, denied, missing, and delete failures have distinct recoverable
  errors without secret content.
- Linux must reject null or plaintext fallback backends. Windows and macOS use their recommended
  OS stores. Environment overrides remain memory-only.
- Migration is idempotent and keeps the legacy copy until verified, allowing rollback to the
  previous Electron release.

## Verification

- Unit tests cover environment priority, shared-store fallback, missing credentials, legacy catalog
  inference, masked setup, backend failures, and secret-free errors.
- Electron tests cover `FORGE_WORKSPACE`, stdin-only helper invocation, successful migration,
  existing-credential preservation, and rollback on failure.
- Integration tests prove a credential written by the desktop path starts both Electron gateway
  and TUI runtime without an environment variable.
- Full Ruff, format, strict mypy, pytest/coverage, Vitest, Electron/Vite builds, Playwright, Bandit,
  package build, and Windows/Linux CI remain required before handoff.

## Out of scope

OAuth login, cloud credential synchronization, account management, plaintext config credentials,
and changing the model/tool protocol are not part of this module.
