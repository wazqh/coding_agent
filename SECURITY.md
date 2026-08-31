# Security policy

Please use GitHub private vulnerability reporting for suspected security issues. Do not include API
keys, access tokens, private repository contents, session logs, or project memories in a public
issue. Include the affected version, operating system, a minimal reproduction, expected boundary,
and observed result.

Forge treats model output, repository instructions, skills, paths, tool arguments, and command
output as untrusted. A report is especially valuable when it demonstrates workspace escape,
approval bypass, destructive-command execution, secret propagation, hash-guard bypass, cross-project
memory access, or trust reuse after a resource changed.

The project supports the latest tagged release. Until a fix is available, stop using the affected
feature, disable project trust and memory, and use read-only permissions where possible.

## Desktop boundary

Electron supervises a Python gateway bound to an OS-assigned `127.0.0.1` port. The gateway requires
an exact Host/Origin match, exchanges a one-time capability for an HttpOnly SameSite=Strict cookie,
and accepts one controlling WebSocket. The renderer is sandboxed with context isolation and no Node
integration; its preload bridge exposes only allowlisted workspace, trust, lifecycle, and credential
operations. The desktop endpoint is not intended for LAN or hosted access.

Provider API keys are resolved from an explicit environment variable or the operating-system
credential service. `models.toml` stores provider/model metadata and a credential reference only.
Keys must not enter renderer state, WebSocket messages, session JSONL, Memory, Skills, logs, CLI
arguments, screenshots, or test fixtures. A backend that cannot provide secure persistence may keep
a key for the current process, but must not fall back to a plaintext file.

## Review and execution boundary

File previews and change review resolve workspace-relative paths through the same confined path
service and reject traversal, absolute paths, binary data, oversize text, and symlink/junction
escapes. Accepting a change records review state only. Undo is allowed only while the current file
matches the recorded post-change hash; otherwise Forge returns a recoverable conflict rather than
overwriting newer work.

Hard-destructive commands are rejected before approval and cannot be enabled by `auto` permissions,
verification settings, or GUI controls. Other writes and commands retain the ordinary approval,
secret-stripped environment, timeout, output limit, cancellation, and process-tree termination
boundaries. Hard-rule matching is semantic: Forge checks the resolved executable, action flags,
dry-run or `-WhatIf` state, target type, wrappers, and nested shell payloads. A risky word used as
search text or a formatter subcommand is not itself a hard block. Encoded shell payloads remain
blocked because they cannot be reviewed before execution. A UI defect or a model instruction must
never be treated as authorization to weaken these checks.
