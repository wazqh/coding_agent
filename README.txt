Forge Coding Agent

Git 仓库：https://github.com/wazqh/coding_agent

Forge 是个人独立实现的本地编程智能体，核心模型—工具—观察循环、上下文与会话、工具执行、审批、安全策略、Memory 和 Skills 均自行编写，不依赖 Agent 框架或服务端代码执行。支持 Python 3.11/3.12、Windows/Linux，提供保留终端滚屏的 TUI 与 Electron + React 桌面端；两者共用同一个 Python AgentController。

TUI 运行：`python -m pip install -e .`，配置模型后执行 `python -m coding_agent --cwd .`。桌面端运行：`python -m pip install -e ".[desktop]"`，进入 `web` 目录执行 `npm ci`，PowerShell 设置 `$env:FORGE_WORKSPACE=(Resolve-Path ..).Path`，再执行 `npm run desktop:dev`。模型可在桌面“模型设置”或 TUI `/model add` 中配置；API Key 只进入系统凭据库或环境变量，不写入仓库、models.toml、会话、Memory 或前端协议。

特色：项目化会话恢复与压缩；计划和工具轨迹；文件读写、命令、符号检索；三档权限与写前 Diff 审批；越界路径、并发覆盖和高风险命令硬阻断；可恢复变更账本、统一/并排 Diff 与安全撤销；项目命令推荐、手动/自动验证、Agent TDD 与两轮失败自修复；受信任 AGENTS.md、懒加载 SKILL.md 和项目记忆。桌面端提供 `/`、`@file`、`$skill` 补全、语法高亮只读预览、模型管理和任务检查器，不展示隐藏思维链或原始协议 JSON。

验证命令与详细设计见 README.md、docs/architecture.md、docs/roadmap.md 和 docs/demo-script.md。提交视频使用真实模型完成一次读代码—修改—审批—验证—Diff 审查闭环，时长不超过 2 分钟、MP4 不超过 200 MB，且不出现任何凭据。
