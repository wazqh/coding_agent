import type { ReactNode } from "react";

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
  onVerify?: (turnId: string) => void;
  onRepair?: (turnId: string) => void;
  showRaw?: boolean;
  working?: {
    status: string;
    step: number;
    maxSteps: number;
    contextLeft: number;
  } | null;
}

type WorkItem = Extract<
  TimelineItem,
  { kind: "activity" | "approval" | "plan" | "error" }
>;

function isWorkItem(item: TimelineItem): item is WorkItem {
  return (
    item.kind === "activity" ||
    item.kind === "approval" ||
    item.kind === "plan" ||
    item.kind === "error"
  );
}

const workingLabels: Record<string, string> = {
  thinking: "正在思考",
  planning: "正在规划",
  tool_pending: "准备执行工具",
  awaiting_approval: "等待审批",
  executing: "正在执行",
  observing: "正在整理结果",
  validating: "正在验证",
};

function completionLabel(item: Extract<TimelineItem, { kind: "completion" }>): string {
  if (item.validationStatus === "failed" && ["completed", "failed"].includes(item.status)) {
    return "已完成 · 验证失败";
  }
  if (item.status === "completed") {
    if (item.validationStatus === "passed") return "已完成 · 验证通过";
    if (item.validationStatus === "failed") return "已完成 · 验证失败";
    if (item.validationStatus === "incomplete") return "正在验证";
    return "已结束 · 未验证";
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
  onVerify,
  onRepair,
  showRaw = false,
  working = null,
}: TimelineProps) {
  const activePlanId = working
    ? [...items].reverse().find((item) => item.kind === "plan")?.id
    : undefined;

  const renderWorkItem = (item: WorkItem): ReactNode => {
    if (item.kind === "activity") {
      return item.activityKind === "validation" ? (
        <ValidationCard item={item} key={item.id} />
      ) : (
        <ActivityRow
          item={item}
          showRaw={showRaw}
          onApproval={onApproval}
          approvalAvailable={approvalAvailable}
          key={item.id}
        />
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
    return null;
  };

  const rendered: ReactNode[] = [];
  let trace: WorkItem[] = [];
  const flushTrace = () => {
    if (!trace.length) return;
    const current = trace;
    trace = [];
    rendered.push(
      <section className="execution-trace" aria-label="执行轨迹" key={`trace:${current[0].id}`}>
        {current.map(renderWorkItem)}
      </section>,
    );
  };

  items.forEach((item, index) => {
    if (isWorkItem(item)) {
      trace.push(item);
      return;
    }
    flushTrace();
    if (item.kind === "user") {
      const startsNewTurn = index > 0 && items[index - 1]?.kind === "completion";
      rendered.push(
        <article
          className={`user-turn${startsNewTurn ? " starts-new-turn" : ""}`}
          data-lane="user"
          key={item.id}
        >
          <span>您</span>
          <p>{item.content}</p>
        </article>,
      );
      return;
    }
    if (item.kind === "assistant") {
      rendered.push(
        <article
          className={`assistant-turn${item.streaming ? " is-streaming" : ""}`}
          data-lane="agent"
          aria-label="Agent 回复"
          key={item.id}
        >
          <MarkdownMessage content={item.content} streaming={item.streaming} />
        </article>,
      );
      return;
    }
    rendered.push(
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
        {item.status === "completed" && item.validationStatus === "not_run" && item.turnId ? (
          <button
            type="button"
            className="completion-action"
            aria-label="验证此轮"
            onClick={() => onVerify?.(item.turnId!)}
          >
            验证
          </button>
        ) : null}
        {["completed", "failed"].includes(item.status) && item.validationStatus === "failed" && item.turnId ? (
          <button
            type="button"
            className="completion-action is-repair"
            aria-label="修复验证失败"
            onClick={() => onRepair?.(item.turnId!)}
          >
            修复
          </button>
        ) : null}
      </div>,
    );
  });
  flushTrace();

  return (
    <div className="timeline" role="feed" aria-label="Agent 执行记录">
      {rendered}
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
