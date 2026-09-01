Forge Coding Agent

Git 仓库：https://github.com/wazqh/coding_agent

Forge 是个人与 Codex 协作实现的本地编程智能体。模型—工具—观察循环、上下文、会话、审批、安全、Memory 与 Skills 均自行编写，不依赖 Agent 框架、托管执行或远程文件服务。支持 Python 3.11/3.12、Windows/Linux，演示界面为 Electron + React 桌面端。

启动：`python -m pip install -e ".[desktop]"`；进入 `web` 执行 `npm ci`；设置 `$env:FORGE_WORKSPACE=(Resolve-Path ..).Path`；运行 `npm run desktop:dev`。模型与 OpenAI-compatible 服务商在任务检查器中配置；API Key 只进入系统凭据库或显式环境变量，不写入仓库、会话、Memory、`models.toml` 或前端协议。

特色：可恢复 Session 与上下文压缩；可见计划、工具轨迹和 Markdown 结果；`/`、`@file`、`$skill` 补全；文件、命令与符号级导航；三档权限；写前 Diff 审批；越界与高风险操作硬阻断；持久化变更账本、统一/并排审查及冲突安全 Undo。每个 Session 独立保存关闭、规则验证或 Agent TDD 合同。Agent 可登记聚焦验证规则，确定性验证层负责执行并区分通过、测试失败、配置错误、拒绝、超时与取消；纯读取回合不会出现无关验证。不展示隐藏思维链或原始协议 JSON。

演示使用真实模型完成“读取—修改—审批—验证—Diff 审查”闭环。详细设计、启动说明与安全边界见 `README.md`、`docs/architecture.md` 和 `SECURITY.md`。
