# Delivery status and roadmap

This file records the release state after the Electron desktop integration. Electron is the primary
graphical frontend; the scrolling TUI remains a first-class fallback and automation surface. The
loopback React gateway under `web/` is shared desktop infrastructure, not a separately promoted
browser product.

## Implemented now

- Local model-tool-observation loop with structured events, bounded retries, loop guards, visible
  plans, workspace tools, configurable 12–100 step budgets, and resumable JSONL sessions.
- Workspace confinement, hash-guarded atomic writes, visible unified diffs, three-way approvals,
  dangerous-command refusal, secret-stripped child environments, and process-tree cancellation.
- Scrolling prompt-toolkit/Rich interface with normal terminal history, narrow and `NO_COLOR`
  rendering, slash/skill/file completion, live status, and Esc cancellation.
- OpenAI-compatible provider catalog and project-scoped model/permission/step settings, plus Gemini
  function-call compatibility with durable thought signatures.
- Electron main process that supervises the local Python runtime, keeps the renderer sandboxed,
  enforces navigation policy, owns workspace/trust dialogs, and handles credentials outside React
  and the WebSocket protocol.
- React desktop workspace with project-organized sessions, collapsible navigation, activity and plan
  timelines, streaming Markdown, inline approval/Diff review, task inspector, bounded file preview,
  `/`/`@`/`$` completion, session controls, Skills, Memory, context, permissions, steps, and provider
  onboarding. Startup restores the latest meaningful workspace session, session deletion removes
  only its evidenced Memory, and recorded file changes support conflict-safe per-change Undo.
- Human-readable expandable tool details, created/modified/deleted file accounting, rendered
  approval and inspector Diffs, and responsive 1024/1920 layouts with a full-height inspector and
  one composer focus treatment.
- Bundled Noto Sans SC and JetBrains Mono, hashed wheel-contained renderer assets, Python/Vitest
  regression coverage, and a mocked renderer acceptance path at 1024×700 and 1920×1080 on Windows
  and Linux.

## Required follow-up

1. Keep the pushed Ubuntu/Windows, Python 3.11/3.12 and desktop renderer workflow green; package a
   reproducible desktop installer only after the current source delivery is stable.
2. Run the five-task real-model evaluation three times per task in disposable repositories and
   retain pass rate, tool success, corrections, tokens, latency, memory pollution, skill activation,
   and safety evidence outside Git.
3. Perform clean-clone acceptance for TUI and Electron: trust, model onboarding, approval choices,
   cancellation, resume, compact, Memory, Skills, file preview, Diff review, and narrow-window use.
4. Record the two-minute Electron demonstration from the exact release candidate and tag only the
   commit whose CI and manual acceptance evidence are green.

## Optional product work

- Add adaptive, provider-aware reasoning effort without requesting, persisting, or rendering hidden
  chain-of-thought.
- Add measured startup and bundle-size work, large-Diff virtualization, richer session search, and
  OS-specific installer/signing pipelines after functional acceptance.
- Add true Electron-level smoke automation in addition to the existing sandboxed main/preload unit
  tests and browser-driven renderer acceptance path.
- Harden cancellation event ordering and Windows junction/symlink-swap preview races after the
  current bounded read-only preview path has shipped.

## Explicitly out of scope for 1.0

Plugin marketplaces, MCP, multi-agent orchestration, RAG, hosted execution, remote file services,
and a browser code editor remain excluded. A standalone hosted or LAN Web product is deferred; any
future proposal must preserve the same local authority and approval boundary instead of exposing the
desktop gateway remotely.
