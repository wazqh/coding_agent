# Delivery status and roadmap

This file records the state of the implementation after the current interactive-session and
provider-compatibility module. It separates implemented behavior from work that still needs fresh
verification or product decisions.

## Implemented now

- Local model-tool-observation loop with structured events, bounded retries, loop guards, plans,
  workspace tools, and resumable JSONL sessions.
- Workspace path confinement, hash-guarded atomic writes, visible unified diffs, explicit approval
  choices, dangerous-command refusal, secret-stripped child environments, and process-tree
  cancellation.
- Scrolling prompt-toolkit and Rich interface with normal terminal history, narrow/no-color
  rendering, slash/skill/file completion, live status, consistent block spacing, and Esc
  cancellation.
- Detailed slash-command help, session-scoped model and permission management, structured skill and
  memory management, and an interactive recent-session picker with context preview.
- Trusted scoped `AGENTS.md`, lazy repository/user `SKILL.md`, project-isolated approved memory,
  deterministic compaction, and request-only repair of interrupted provider histories.
- OpenAI-compatible streaming plus Gemini function-call compatibility, including durable thought
  signatures and complete-request token estimates that include tool schemas.

## Required follow-up

1. Confirm the pushed workflow on Ubuntu and Windows for Python 3.11 and 3.12, then fix only failures
   that reproduce against the current commit. Recheck a native Windows isolated build; the current
   machine reproduces a `python-build` UTF-8 decode failure while installing Hatchling, while
   `python -m build --no-isolation` successfully builds both distributions.
2. Run the five-task real-model evaluation three times per task in disposable repositories and
   record pass rate, tool success, correction count, tokens, latency, memory pollution, unexpected
   skill activation, and safety leakage. Do not commit generated reports.
3. Perform a clean-clone wheel installation and manual 80-column, `NO_COLOR`, approval, cancellation,
   resume, compact, memory, and skill acceptance pass.
4. Record the two-minute demonstration from the exact release candidate, complete documentation QA,
   and create the release tag only after CI and acceptance evidence are green.

## Optional product work

- Add an **adaptive reasoning budget** policy instead of one hard-coded reasoning setting. It should
  choose a provider-supported effort or token budget from task complexity, tool failures, remaining
  context, and latency/cost limits; expose the selected policy and allow a user override.
- Keep this control model-agnostic and degrade to a configurable static default when an endpoint has
  no reasoning control. Never request, persist, or render private chain-of-thought; the feature
  controls reasoning effort, not disclosure of hidden reasoning.
- Consider richer session filtering, diff navigation for large changes, and measured TUI theme
  variants only after the required acceptance work above.

## Explicitly out of scope for 1.0

Web UI, plugin marketplace, MCP, multi-agent orchestration, RAG, hosted execution, and remote file
services remain excluded unless the product scope is deliberately revised.
