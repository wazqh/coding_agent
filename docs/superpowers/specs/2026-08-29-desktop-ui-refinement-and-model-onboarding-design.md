# Desktop UI Refinement and Model Onboarding Design

## Status

Implemented and integrated on 2026-08-30. This document remains the design rationale; current
startup and verification commands live in the repository README.

## Scope

This module refines the existing Electron V2 frontend without changing the local Python agent loop. It fixes keyboard completion, organizes sessions under projects, makes the inspector entry truthful, enriches execution receipts, and adds a secure `/model` onboarding flow.

## Navigation and layout

- The left rail is a project tree. Projects are first-level nodes and sessions are second-level nodes. The current project starts expanded; inactive projects are collapsed.
- The rail keeps one product identity, one “new conversation” action, project groups, and session titles. Repeated model labels and explanatory runtime copy are removed.
- The collapse control sits on the rail/content divider and remains reachable in both expanded and collapsed modes.
- The right header action is named “任务检查器”. It opens the last selected inspector tab. Tabs are “变更”, “运行设置”, “资源”, and “上下文”.

## Composer completion

- `/`, `@`, and `$` use one completion interaction model.
- Arrow keys move selection without moving the textarea caret. The selected option is scrolled into view.
- Tab applies a completion without sending. Enter applies an incomplete completion, otherwise sends. Escape dismisses the popup.
- The popup is opaque, bounded to the composer width, and preserves textarea focus.

## Execution narrative

- `update_plan` is represented only by the plan card, never by a duplicate tool receipt.
- Routine reads, searches, and listings are grouped as workspace inspection.
- File mutations, commands, validations, approvals, and errors remain distinct receipts.
- Receipts show a meaningful title, subject, status, and expandable structured detail. Validation shows output summary and pass/fail state.
- The plan card highlights the current step, shows progress, and defaults to collapsed after completion. Final assistant output is never collapsed.

## Secure model onboarding

- `/model` and the model control open one model manager. Existing providers can be selected directly; “添加服务商” opens a short form for provider name, base URL, model ID, compatibility, and API key.
- Provider metadata is written to the user-level `models.toml`, never the repository.
- The renderer sends the API key only through a closed Electron IPC method. It is never sent through the WebSocket protocol, Python session history, logs, Memory, or Skills.
- Electron stores the key as an encrypted blob using asynchronous `safeStorage`. On Linux, a `basic_text` backend is rejected. If encrypted storage is unavailable, the key is held only for the current process and the UI explains that it will not survive restart.
- The encrypted credential is decrypted only in the Electron main process and supplied to the Python gateway child as the provider profile's generated environment variable. The renderer receives only capability state and masked metadata.
- Adding a provider restarts the idle local gateway so the new environment and `models.toml` are loaded. Model changes are unavailable while an Agent turn is busy.

## Safety and compatibility

- Renderer sandboxing, context isolation, closed request unions, workspace confinement, and approval boundaries remain unchanged.
- User-facing product names remain sourced from `coding_agent.branding`.
- Python 3.11/3.12 and Windows/Linux remain supported.
- API keys are never persisted in plaintext and are never returned to the renderer after submission.

## Verification

- Component tests cover keyboard selection/scrolling, project-tree hierarchy, inspector naming, and richer activity presentation.
- Electron tests cover credential encryption availability, Linux plaintext rejection, allowlisted IPC payloads, and gateway environment injection without secret output.
- Python tests cover atomic provider profile writes, validation, secret-free model catalog snapshots, and cross-project session grouping.
- The production frontend and Electron bundles must build before visual review; the full repository suite runs before handoff.
