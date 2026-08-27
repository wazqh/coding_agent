# Forge Coding Agent

An original Python 3.11+ CLI coding-agent runtime. The repository is being delivered in tested,
independently reviewable modules; installation and end-user commands will be enabled with the CLI
module.

Current foundation module:

- validated configuration with explicit precedence and environment-only API credentials;
- shared agent event and tool-result contracts;
- OpenAI-compatible streaming adapter with fragmented function-call assembly and bounded retry.

The implementation does not use an agent framework or a hosted code-execution/file service.
