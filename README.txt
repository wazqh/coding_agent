Git 仓库：https://github.com/wazqh/coding_agent
Forge 是个人与 Codex 协作实现的本地编程智能体，不依赖 Agent 框架、托管执行或远程文件服务。支持 Python 3.11+、Windows，提供终端与 Electron 桌面端。
首次启动前必须提供非空模型凭据。全新安装请先设置 `OPENAI_API_KEY`，并按服务设置 Base URL 和模型名称；已有 `models.toml` 时，也可使用其中 `api_key_env` 指定的环境变量或系统凭据库。
PowerShell 启动示例：

```powershell
python -m pip install -e ".[desktop]"
$env:OPENAI_API_KEY = "..."
$env:OPENAI_BASE_URL = "https://your-compatible-endpoint/v1"
$env:CODING_AGENT_MODEL = "your-model"
Set-Location web
npm ci
$env:FORGE_WORKSPACE = (Resolve-Path ..).Path
npm run desktop:dev
```
凭据缺失或为空时，终端模式会报错退出，桌面版会在主页面加载前显示启动错误。成功启动后，可在“任务检查器 → 设置 → 模型”中管理服务商。
特色：可恢复 Session、上下文压缩、计划与工具轨迹、Markdown、`/`/`@file`/`$skill` 补全、三档权限、写前 Diff 审批、安全 Undo、规则验证、skill辅助生成与 Agent TDD。
详细设计、启动说明与安全边界见仓库 `README.md`、`docs/architecture.md` 和 `SECURITY.md`。
