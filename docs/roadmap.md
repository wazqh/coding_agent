# Delivery status and roadmap

This file records the release state after the Electron desktop integration. Electron is the primary
graphical frontend; the scrolling TUI remains a first-class fallback and automation surface. The
loopback React gateway under `web/` is shared desktop infrastructure, not a separately promoted
browser product.

## Implemented now

- Local model-tool-observation loop with structured events, bounded retries, loop guards, visible
  plans, workspace tools, cached symbol outline/definition/reference navigation, configurable
  12–100 step budgets, and resumable JSONL sessions.
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
  `/`/`@`/`$` completion, session controls, review-before-write Skill creation, Memory, context,
  permissions, steps, flat daily model switching, and separate provider onboarding. Startup
  restores the latest meaningful workspace session, session deletion removes
  only its evidenced Memory, and recent-project removal preserves all workspace/session/Memory data.
- Contextual session file tree with collapsible directories, changed/read status, and an adjacent
  workspace-confined read-only preview; full-repository enumeration remains intentionally out of scope.
- Stable operation cards merge approval, execution, and result state; hard-safety blocks use a
  non-overridable shield receipt. The restart-safe change ledger supports accept or conflict-safe
  undo for one or all changes, unified/side-by-side/fullscreen review, and resizable inspection.
- Human-readable tool, run, resource, validation, and context details without raw JSON; project
  verification separates command history from verification controls, offers project-derived
  one-click command suggestions, supports manual or automatic checks plus Agent TDD guidance, and
  feeds failures through at most two bounded repair attempts
  while retaining the ordinary approval, safety, cancellation, and Step-budget boundaries. Turn
  footers distinguish unverified, running, passed, and failed states and expose a visible repair
  action with the failed evidence.
- Bundled Noto Sans SC and JetBrains Mono, hashed wheel-contained renderer assets, Python/Vitest
  regression coverage, and a mocked renderer acceptance path at 1024×700 and 1920×1080 on Windows
  and Linux.
- Review-surface hierarchy with WCAG-readable secondary text, semantic command rows, stronger active
  tabs, directory guide lines, shared code metrics, thin scrollbars, reduced-motion fallbacks, and
  content-sized Diff controls that cannot be covered by the scrolling review body. Common source
  files receive lazy syntax highlighting in the read-only preview; Diff colors retain priority.

## Required follow-up

1. Run the complete Ubuntu/Windows, Python 3.11/3.12 and desktop renderer workflow on the exact
   candidate commit. The source-delivered Electron client is the assessment target; an installer is
   not required by the brief.
2. Run the five-task real-model evaluation three times per task in disposable repositories and
   retain pass rate, tool success, corrections, tokens, latency, memory pollution, skill activation,
   and safety evidence outside Git.
3. Perform clean-clone acceptance for TUI and Electron: trust, model onboarding, approval choices,
   cancellation, resume, compact, Memory, Skills, file preview, Diff review, and narrow-window use.
4. Confirm `README.txt` remains within 1000 Chinese characters and contains the public repository
   URL. Record the at-most-two-minute, at-most-200-MB MP4 from the exact candidate, then stop pushing
   after the 2026-09-02 24:00 China Standard Time deadline.

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
