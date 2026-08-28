Forge Coding Agent 是原创 Python 3.11+ 命令行编程智能体，不依赖任何 agent 框架。它提供普通终端滚动式 TUI、自研模型—工具—观察循环、计划、审批、会话恢复、上下文压缩、项目记忆、AGENTS.md 和懒加载 SKILL.md。

安装：python -m pip install -e .
凭据只通过 OPENAI_API_KEY 提供；可选 OPENAI_BASE_URL、CODING_AGENT_MODEL。启动：coding-agent --cwd . 或 python -m coding_agent --cwd .。单次任务：coding-agent run "任务" --output jsonl；恢复：coding-agent resume SESSION_ID；列表：coding-agent sessions。

安全机制包括工作区路径隔离、符号链接越界阻止、SHA-256 并发保护、原子写入、统一 diff、分级审批、危险命令直接拒绝、秘密环境变量剥离、超时终止进程树及输出截断。非交互审批失败返回 3。

项目记忆默认关闭，只保存用户确认且不含秘密的经验，并按仓库隔离。技能从仓库或用户 .agents/skills 发现，激活后才读取完整说明，脚本不会自动执行。项目资源首次使用必须信任，哈希变化后重新确认。

验证：python -m pytest；python -m ruff check .；python -m mypy。CI 覆盖 Ubuntu/Windows 与 Python 3.11/3.12，不配置真实 API key。真实模型评测含 5 个隔离任务，每个重复 3 次。详细说明见 README.md，演示脚本见 docs/demo-script.md。
