# Forge Coding Agent

An original Python 3.11+ CLI coding-agent runtime. The repository is being delivered in tested,
independently reviewable modules; installation and end-user commands will be enabled with the CLI
module.

Implemented modules:

- validated configuration with explicit precedence and environment-only API credentials;
- shared agent event and tool-result contracts;
- OpenAI-compatible streaming adapter with fragmented function-call assembly and bounded retry.
- workspace-confined file tools with hash-guarded atomic edits and centralized approvals;
- screened command execution with secret stripping, timeout, process-tree termination, and bounded output;
- a local model-tool-observation loop with visible plans, loop guards, budgets, cancellation, and JSONL sessions;
- resumable conversation state and deterministic context compaction that preserves the original transcript.

The interactive CLI, project memory, trusted project instructions, and skills are intentionally
delivered in later modules and are not advertised as available yet.

The implementation does not use an agent framework or a hosted code-execution/file service.
