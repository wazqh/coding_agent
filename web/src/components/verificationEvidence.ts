import type { TimelineItem } from "../state/store";

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
}

function valueText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function buildVerificationRepairTask(items: TimelineItem[], turnId: string): string {
  const failed = [...items].reverse().find(
    (item): item is Extract<TimelineItem, { kind: "activity" }> =>
      item.kind === "activity" &&
      item.activityKind === "validation" &&
      item.turnId === turnId &&
      item.status === "failed",
  );
  const detail = record(failed?.detail);
  const data = record(detail.data);
  const command = valueText(data.command) || "（未记录命令）";
  const summary = valueText(detail.summary) || failed?.summary || "验证未通过";
  const output =
    valueText(data.stderr) ||
    valueText(data.stdout) ||
    valueText(data.output) ||
    "（未记录命令输出）";

  return [
    "请修复以下验证失败，并在修改后重新运行验证。",
    "",
    `验证命令：${command}`,
    `失败摘要：${summary}`,
    "验证输出：",
    "```text",
    output.slice(0, 12_000),
    "```",
  ].join("\n");
}
