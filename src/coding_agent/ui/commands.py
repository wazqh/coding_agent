from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommandSpec:
    name: str
    usage: tuple[str, ...]
    description: str
    details: str


COMMAND_SPECS = (
    SlashCommandSpec(
        "/help",
        ("/help", "/help COMMAND"),
        "查看命令说明或某个命令的详细用法。",
        "COMMAND 可以写成 help 或 /help。",
    ),
    SlashCommandSpec(
        "/status",
        ("/status",),
        "查看当前会话、模型、安全模式、上下文和资源状态。",
        "这是只读命令，不会修改会话。",
    ),
    SlashCommandSpec(
        "/model",
        ("/model", "/model MODEL_ID"),
        "查看或切换当前进程使用的模型。",
        "切换只影响当前进程及随后新建或恢复的会话，不修改项目配置。",
    ),
    SlashCommandSpec(
        "/permissions",
        ("/permissions", "/permissions prompt|auto|read-only"),
        "查看或切换工具审批策略。",
        "切换模式会清除之前的会话内授权，避免授权跨策略复用。",
    ),
    SlashCommandSpec(
        "/plan",
        ("/plan",),
        "显示当前会话的计划及步骤状态。",
        "计划由 update_plan 工具维护；该命令不会让模型自动创建计划。",
    ),
    SlashCommandSpec(
        "/diff",
        ("/diff",),
        "显示本进程中已批准并应用的文件修改 diff。",
        "它不是 git diff 的替代品，也不会显示启动前已有的工作区改动。",
    ),
    SlashCommandSpec(
        "/memory",
        (
            "/memory [list]",
            "/memory on|off",
            "/memory remember TEXT",
            "/memory forget ID",
            "/memory clear confirm",
        ),
        "管理当前项目的长期记忆。",
        "开关只影响当前进程；写入按项目隔离。clear 必须显式确认。",
    ),
    SlashCommandSpec(
        "/skills",
        (
            "/skills [list]",
            "/skills search QUERY",
            "/skills enable|disable NAME",
            "/skills reload",
        ),
        "浏览和管理当前会话可用的 SKILL.md 技能。",
        "启用状态属于当前会话；reload 会保留本会话的禁用选择。",
    ),
    SlashCommandSpec(
        "/compact",
        ("/compact",),
        "压缩较早的会话上下文并保留最近交互。",
        "原始 JSONL 会话记录不会被删除。上下文较短时不会执行压缩。",
    ),
    SlashCommandSpec(
        "/resume",
        ("/resume", "/resume SESSION_ID"),
        "选择最近会话，或按 ID 切换到指定的可恢复会话。",
        "不带参数时列出当前工作区的最近会话；审批授权不会跨会话继承。",
    ),
    SlashCommandSpec(
        "/new",
        ("/new",),
        "保存当前会话并创建一个干净的新会话。",
        "工作计划、会话审批和已激活技能都会重置。",
    ),
    SlashCommandSpec(
        "/clear",
        ("/clear",),
        "清理当前终端显示。",
        "不会删除对话、会话记录、计划或工作区文件。",
    ),
    SlashCommandSpec(
        "/raw",
        ("/raw", "/raw on|off"),
        "查看或设置工具结果是否显示完整原始内容。",
        "不带参数时仅显示当前状态，不再盲目切换。",
    ),
    SlashCommandSpec(
        "/exit",
        ("/exit",),
        "保存会话并退出交互界面。",
        "退出时会显示 session ID 和可复制的恢复命令。",
    ),
)

COMMAND_BY_NAME = {spec.name: spec for spec in COMMAND_SPECS}
SLASH_COMMANDS = [spec.name for spec in COMMAND_SPECS]


def normalize_command_name(value: str) -> str:
    name = value.strip().casefold()
    return name if name.startswith("/") else "/" + name
