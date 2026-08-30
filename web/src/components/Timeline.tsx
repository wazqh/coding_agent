import type { ApprovalDecision } from "../protocol/types";
import type { TimelineItem } from "../state/store";
import { ActivityRow } from "./ActivityRow";
import { ApprovalCard } from "./ApprovalCard";
import { MarkdownMessage } from "./MarkdownMessage";
import { PlanBlock } from "./PlanBlock";
import { ValidationCard } from "./ValidationCard";

interface TimelineProps {
  items: TimelineItem[];
  onApproval: (approvalId: string, decision: ApprovalDecision) => boolean;
  approvalAvailable?: boolean;
  showRaw?: boolean;
  working?: {
    status: string;
    step: number;
    maxSteps: number;
    contextLeft: number;
  } | null;
}

const workingLabels: Record<string, string> = {
  thinking: "正在思考",
  planning: "正在规划",
  tool_pending: "准备执行工具",
  awaiting_approval: "等待审批",
  executing: "正在执行",
  observing: "正在整理结果",
};

function completionLabel(item: Extract<TimelineItem, { kind: "completion" }>): string {
  if (item.status === "completed") {
    if (item.validationStatus === "passed") return "完成 · 验证通过";
    if (item.validationStatus === "failed") return "完成 · 验证失败";
    if (item.validationStatus === "incomplete") return "已完成 · 验证未完成";
    return "已完成";
  }
  const terminal =
    item.status === "failed"
      ? "执行失败"
      : item.status === "interrupted"
        ? "已中断"
        : item.status === "cancelled"
          ? "已停止"
          : "已结束";
  const validation =
    item.validationStatus === "passed"
      ? "验证通过"
      : item.validationStatus === "failed"
        ? "验证失败"
        : item.validationStatus === "incomplete"
          ? "验证未完成"
          : "未运行验证";
  return `${terminal} · ${validation}`;
}

export function Timeline({
  items,
  onApproval,
  approvalAvailable = true,
  showRaw = false,
  working = null,
}: TimelineProps) {
  const activePlanId = working
    ? [...items].reverse().find((item) => item.kind === "plan")?.id
    : undefined;
  return (
    <div className="timeline" role="feed" aria-label="Agent 执行记录">
      {items.map((item) => {
        if (item.kind === "user") {
          return (
            <article className="user-turn" key={item.id}>
              <span>您</span>
              <p>{item.content}</p>
            </article>
          );
        }
        if (item.kind === "assistant") {
          return (
            <article className={`assistant-turn${item.streaming ? " is-streaming" : ""}`} key={item.id}>
              <div className="section-rule">
                <span>Agent</span>
              </div>
              <MarkdownMessage content={item.content} streaming={item.streaming} />
            </article>
          );
        }
        if (item.kind === "activity") {
          return item.activityKind === "validation" ? (
            <ValidationCard item={item} key={item.id} />
          ) : (
            <ActivityRow item={item} showRaw={showRaw} key={item.id} />
          );
        }
        if (item.kind === "approval") {
          return (
            <ApprovalCard
              item={item}
              onApproval={onApproval}
              available={approvalAvailable}
              key={item.id}
            />
          );
        }
        if (item.kind === "plan") {
          return <PlanBlock steps={item.steps} active={item.id === activePlanId} key={item.id} />;
        }
        if (item.kind === "error") {
          return (
            <section className={`error-row is-${item.severity}`} key={item.id}>
              <strong>{item.severity === "warning" ? "警告" : "错误"}</strong>
              <span>{item.message}</span>
            </section>
          );
        }
        return (
          <div
            className={`completion-row is-${item.status} validation-${item.validationStatus}`}
            key={item.id}
          >
            <span>
              {item.status === "interrupted" || item.status === "cancelled"
                ? "■"
                : item.status === "failed"
                  ? "!"
                : item.validationStatus === "passed"
                  ? "✓"
                  : item.validationStatus === "failed"
                    ? "!"
                    : "○"}
            </span>
            <strong>{completionLabel(item)}</strong>
            {item.reason && item.reason !== "assistant completed" ? <small>{item.reason}</small> : null}
          </div>
        );
      })}
      {working ? (
        <div
          className="working-row"
          data-status={working.status}
          role="status"
          aria-label="当前执行状态"
          aria-live="polite"
        >
          <span className="working-motion" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <strong>{workingLabels[working.status] ?? "正在执行"}</strong>
          <small>
            · step {working.step}/{working.maxSteps} · {working.contextLeft}% context left
          </small>
        </div>
      ) : null}
    </div>
  );
}
