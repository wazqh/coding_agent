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
