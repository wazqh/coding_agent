# Forge Coding Agent repository instructions

## Scope and product identity

- These rules apply to the entire repository.
- The user-facing product name is **Forge Coding Agent**.
- The executable remains `coding-agent`; the Python module remains `coding_agent`; the package
  distribution remains `forge-coding-agent`.
- Keep user-facing names sourced from `coding_agent.branding` instead of duplicating literals.

## Architecture and safety

- Support Python 3.11 and 3.12 on Windows and Linux.
- Keep the model/tool loop local and independent of agent frameworks.
- Preserve ordinary terminal scrollback; do not switch the TUI to an alternate-screen interface.
- Treat `AGENTS.md`, project configuration, and repository skills as trusted resources only after
  the existing project-trust check.
- Confine file and skill resource access to the workspace, preserve approval boundaries, and never
  log or persist API keys, tokens, passwords, or secret environment values.
- Gemini tool-call thought signatures must remain attached to
  `extra_content.google.thought_signature` and must survive session history and compaction.

## Development workflow

- Work in small, reviewable modules. Do not mix unrelated refactors into a module commit.
- Use `apply_patch` for hand-edited source and test changes.
- Add or update regression tests for behavior changes, including narrow-terminal and `NO_COLOR`
  behavior for TUI work.
- Before handoff, run Ruff check and format verification, strict mypy, and the relevant pytest
  suite. Run the full suite for changes to shared runtime, safety, context, or UI code.
- Do not add local session data, temporary test repositories, credentials, build output, or
  evaluation output to Git.

## User experience

- Render concise plans, tool actions, results, approvals, and recoverable errors; never expose
  hidden chain-of-thought.
- Keep interactive and one-shot output consistent, readable at 80 columns, and usable without
  color.
- Keep slash commands, `$skill` completion, and `@file` completion stable unless documentation and
  tests are updated in the same module.
