# Session Verification Contract Design

## Scope

This design replaces the desktop client's project-global verification switch with a durable,
session-scoped verification contract. It applies to the Electron GUI and the shared local runtime
used by that GUI. It does not redesign the TUI.

## Product model

Each session owns exactly one verification contract with one of three mutually exclusive modes:

- `off`: no automatic verification; a file-changing turn may still be verified manually.
- `checks`: after an applicable file-changing turn, the deterministic verification layer runs the
  enabled rules that cover the changed paths.
- `agent_tdd`: the Agent writes separate framework-native tests and registers focused rules with
  `register_verification`; the deterministic layer, not the Agent, executes those rules.

An `agent_tdd` contract is valid with no rules. This is the expected initial state: the GUI explains
that the Agent has not registered a rule yet, and the Agent receives an explicit instruction to
create tests and register the working directory, command, covered paths, and timeout.

## Persistence and isolation

The current contract is appended to the session JSONL as a `verification_config` record. Manual
and automatic outcomes are appended as `verification_result` records tied to the target turn.
Restoring a session restores its latest contract and results. Creating a session starts with mode
`off`; deleting the session removes its verification data with the JSONL.

Legacy workspace verification rules remain readable as importable templates. They are never
silently enabled in a new or resumed session. Workspace `max_steps` remains project-scoped.

## Rules, suggestions, and procedures

Each rule carries an ID, label, kind, command, workspace-relative working directory, timeout,
source, enabled flag, and optional covered paths. Suggestions use the same structure and identify
their project root. A workspace-root rule is labelled as a full-project check and is not selected by
default when a narrower project root is available.

Users may add short verification procedures such as “when dependency files change, rerun the
existing test and build rules”. Procedures are session-scoped, visible and editable in the GUI, and
included in the Agent system prompt. Saving a rule authorizes only its exact command and resolved
workspace-relative directory inside that Session. Any changed command/directory returns to normal
approval, and hard safety, path confinement, cancellation, timeouts, and the Step budget remain
non-overridable.

## Execution and evidence

Automatic verification is considered only when a turn created or modified files. Rules are
filtered against that turn's changed paths. Manual verification uses the same filtering; if no rule
matches, the GUI opens verification setup and explains why instead of running every rule.

The lifecycle distinguishes registration approval from deterministic execution. An exact saved
rule does not ask for a second approval when the verification layer runs it. Results preserve these terminal
states without flattening: `passed`, `test_failed`, `configuration_error`, `approval_denied`,
`timed_out`, `cancelled`, and `not_configured`. Only tool events explicitly marked
`verification: true` count as deterministic evidence. An Agent-initiated `pytest`, `ruff`, `mypy`,
or `npm test` command remains an ordinary command observation.

Verification records include queue, approval-wait, and execution durations when available. Repair
is offered only for `test_failed`; configuration errors open the rule editor. Repair context includes
the failed rule ID, command, working directory, covered paths, and bounded output.

## Ordering

Assistant text from a model response that also contains tool calls is rendered as an Agent note in
the execution trace. Only a terminal assistant response with no tool calls is rendered as the final
answer. This prevents text, plan updates, and verification receipts from appearing out of order in
live rendering or after session replay.

## GUI

The Run → Verification surface uses one mode selector instead of an automatic switch plus a TDD
checkbox. It supports rule editing, structured project suggestions, template import, manual
procedures, visible save confirmation, and per-result explanations. Status copy is direct:

- read-only turn: `已完成`
- changed turn with no evidence: `已结束 · 未验证`
- active registration approval: `等待登记验证规则`
- active command: `正在验证`
- pass: `已完成 · 验证通过`
- test failure: `已完成 · 验证失败`

All controls provide immediate visible feedback and remain meaningful without animation.

## Tests

Regression coverage must prove session isolation, resume, deletion, empty Agent TDD setup,
procedure prompt injection, turn-path filtering, structured suggestions, status preservation,
deterministic-evidence separation, result replay, approval timing labels, ordering, and repair/error
actions. Shared runtime and UI changes require the full Python and web test/build matrix.
