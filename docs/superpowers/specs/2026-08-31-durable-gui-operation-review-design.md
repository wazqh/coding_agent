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
- Keep CLI and TUI event behavior compatible.
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

The Run tab presents normalized command and validation history with commands, exit codes, duration,
and human-readable output. Resources presents files touched or read during the turn. Context presents
one consistent used-token metric and an explicitly approximate category breakdown.

## Verification hooks

Trusted project configuration may define verification commands. After a turn that changed files,
the runtime executes configured checks through the existing command safety and approval policy.
Failures are returned to the model for at most two repair attempts, within the existing step budget.
The GUI shows deterministic check results separately from the model's final prose.

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
