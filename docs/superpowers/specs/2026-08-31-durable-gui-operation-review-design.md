# Durable GUI Operation and Review Design

## Status

Implemented in the current 2026-08-31 delivery candidate. This document records the accepted
operation/change-review architecture; use `README.md` for launch instructions and `docs/roadmap.md`
for the remaining release gates.

## Goal

Make the Electron GUI the authoritative, reviewable presentation of an agent turn: approvals,
tool execution, file changes, validation, and context usage remain understandable during the turn
and after the application is restarted.

## Constraints

- Preserve the local Python controller and its safety boundaries.
- Do not expose chain-of-thought or raw protocol JSON.
- Keep headless CLI event behavior compatible.
- Never persist credentials or secret environment values.
- Restored undo is permitted only when the current file still matches the recorded post-change hash.
- Hard safety rules remain non-overridable.

## Operation lifecycle

Every tool call owns one stable `operation_id`, equal to its model tool-call ID. The controller
places that ID in `ToolContext`; approval request/resolution, tool call, and tool result events carry
the same ID. The presenter therefore updates one operation instead of guessing relationships from
command text.

The GUI renders the lifecycle as one row/card:

1. approval required;
2. approved, denied, or blocked;
3. executing;
4. completed or failed.

Completed read-only operations are grouped per turn into an expandable exploration phase. Mutating,
validation, approval, and failed operations remain individually visible. Hard-blocked commands use
a shield treatment and state that execution stopped before workspace mutation.

## Durable change ledger

File tools append bounded change records to the session JSONL. A record contains the change ID,
relative path, kind, unified diff, bounded pre-change text, post-change SHA-256, reversibility, and
review state. Later records mark changes reviewed or reverted; history is append-only.

On session restore, the controller rebuilds the visible change ledger. A reversible record remains
undoable only if its backup exists and the current file matches the post-change hash. Stale or
conflicting records remain visible for audit but cannot overwrite external edits.

`Accept all` marks pending records reviewed without touching files. `Discard all` reverts records in
reverse order and stops at the first conflict, returning an explicit partial-result report.

## Inspector

The inspector width is resizable within safe viewport bounds and stored as a local UI preference.
The Changes tab provides:

- pending/reviewed totals;
- accept/discard all controls;
- per-file accept/discard controls;
- unified and side-by-side views;
- an enlarged review view.

The Run tab separates normalized command history from verification setup and evidence so routine
command output does not bury the validation state. Resources presents files touched or read during
the turn and opens a workspace-confined, syntax-highlighted read-only preview beside the tree.
Context presents one consistent used-token metric and an explicitly approximate category breakdown.

## Verification hooks

This original project-scoped hook design is superseded by the Session Verification Contract design.
Trusted project configuration may still define structured verification templates, but the active
mode, rules, procedures, and results belong to the current Session. Each rule carries its kind,
command, timeout, covered paths, and workspace-relative working directory; legacy command lists are
exposed as templates rooted at `.`.
Manual checks use the same tool path without invoking the model. With automatic verification
enabled for the Session, a turn that changed files executes applicable rules
through the existing command safety and approval policy before candidate final prose is released.
Test failures are returned to the model for at most two repair attempts, within the existing step
budget. Configuration, approval, timeout, and cancellation outcomes remain terminal rather than
being misreported as code failures.
The GUI shows deterministic check results separately from the model's prose and exposes visible
unverified, running, passed, and failed states. Agent TDD guides the model to create separate native
test artifacts and declare a Session rule, but does not move automatic execution authority
into the model.

When the check list is empty, the runtime reads small workspace-confined project markers and the
GUI presents matching commands as compact suggestion controls. Detection does not execute commands,
follow directory symlinks, or silently save a choice; configuration remains an explicit user action.

Real-time subprocess streaming and skipping arbitrary Plan items are excluded: the current command
runner returns completed results, and Plan entries are descriptive state rather than scheduled jobs.

## Session metadata

After the first completed user turn, a deterministic local title normalizer creates a concise title
and persists it as session metadata. This does not add a model request. Existing sessions without a
stored title continue to fall back to their first user message.

Projects may be removed from Forge's recent-project index through an explicit confirmation dialog
that displays the workspace path. This operation never deletes workspace or Git files and preserves
session and Memory data so reopening the directory remains recoverable. Destructive project-data
clearing is a separate operation and is not part of ordinary project removal.
