Forge Coding Agent

Git 仓库：https://github.com/wazqh/coding_agent

Forge 是个人与codex合作实现的本地编程智能体，模型—工具—观察循环、上下文、会话、审批、安全、Memory 和 Skills 均自行编写，不依赖 Agent 框架或服务端执行。支持 Python 3.11+、Windows/Linux，有 Electron + React 桌面端。

TUI：`python -m pip install -e .` 后运行 `python -m coding_agent --cwd .`。桌面端：安装 `.[desktop]`，在 `web` 执行 `npm ci`，设置 `$env:FORGE_WORKSPACE=(Resolve-Path ..).Path`，再运行 `npm run desktop:dev`。模型可在桌面或 TUI `/model add` 配置；API Key 只进入系统凭据库或环境变量，不写入仓库、会话、Memory 或前端协议。

特色：会话恢复与压缩、计划与工具轨迹、文件/命令/符号工具、三档权限、写前 Diff 审批、越界和高风险命令硬阻断、可恢复变更账本及统一/并排审查。每个 Session 独立保存关闭、规则验证或 Agent TDD 合同，并支持相对工作目录、目标路径、嵌套项目建议与人工检验规程；保存规则只授权当前 Session 中完全相同的命令和工作目录，硬安全规则仍不可覆盖。Agent 用 `register_verification` 登记聚焦规则，确定性验证层区分通过、测试失败、配置错误、拒绝、超时和取消，真实测试失败最多自修复两轮。模型复制复用同一服务商、Base URL 和系统凭据，只要求填写新的 Model ID。纯读取回合直接完成。桌面端还提供 `/`、`@file`、`$skill` 补全、语法高亮预览、模型管理、任务检查器、AGENTS.md、Skills 和项目记忆；不展示隐藏思维链或原始协议 JSON。

详细设计见 README.md 与 docs/。演示使用真实模型完成读代码—修改—审批—验证—Diff 审查闭环；MP4 不超过 2 分钟、200 MB，且不出现凭据。
