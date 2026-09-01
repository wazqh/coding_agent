import { useState } from "react";

import type { ApprovalDecision } from "../protocol/types";
import type { TimelineItem } from "../state/store";
import { ApprovalCard } from "./ApprovalCard";
import { ChevronIcon, ShieldIcon } from "./icons";
import { MarkdownMessage } from "./MarkdownMessage";
import { StructuredToolDetail } from "./StructuredToolDetail";

type Activity = Extract<TimelineItem, { kind: "activity" }>;

interface ActivityStep {
  name: string;
  subject: string;
  status: string;
  summary: string;
}

function activitySteps(detail: unknown): ActivityStep[] {
  if (typeof detail !== "object" || detail === null || !("steps" in detail)) return [];
  const steps = (detail as { steps?: unknown }).steps;
  if (!Array.isArray(steps)) return [];
  return steps.flatMap((step) => {
    if (typeof step !== "object" || step === null) return [];
    const value = step as Record<string, unknown>;
    return [{
      name: typeof value.name === "string" ? value.name : "tool",
      subject: typeof value.subject === "string" ? value.subject : "执行工具",
      status: typeof value.status === "string" ? value.status : "running",
      summary: typeof value.summary === "string" ? value.summary : "",
    }];
  });
}

function isHardBlocked(detail: unknown): boolean {
  if (typeof detail !== "object" || detail === null) return false;
  const result = "raw" in detail
    ? (detail as { raw?: unknown }).raw
    : detail;
  if (typeof result !== "object" || result === null) return false;
  const value = result as Record<string, unknown>;
  const data = typeof value.data === "object" && value.data !== null
    ? value.data as Record<string, unknown>
    : {};
  return value.code === "DANGEROUS_COMMAND" || data.hard_blocked === true;
}

function agentNoteMarkdown(detail: unknown): string | null {
  if (typeof detail !== "object" || detail === null || !("markdown" in detail)) return null;
  const markdown = (detail as { markdown?: unknown }).markdown;
  return typeof markdown === "string" ? markdown : null;
}

interface ActivityRowProps {
  item: Activity;
  showRaw?: boolean;
  onApproval?: (approvalId: string, decision: ApprovalDecision) => boolean;
  approvalAvailable?: boolean;
}

export function ActivityRow({
  item,
  showRaw = false,
  onApproval = () => false,
  approvalAvailable = true,
}: ActivityRowProps) {
  const steps = activitySteps(item.detail);
  const structured = steps.length > 0;
  const hardBlocked = isHardBlocked(item.detail);
  const noteMarkdown = item.activityKind === "agent_note" ? agentNoteMarkdown(item.detail) : null;
  const [expanded, setExpanded] = useState(structured);
  const detailVisible = showRaw || (!structured && expanded && noteMarkdown === null);
  const statusIcon =
    hardBlocked
      ? <ShieldIcon className="hard-block-shield" />
      : item.status === "failed"
      ? "!"
      : item.status === "completed"
        ? "✓"
        : item.activityKind === "command"
          ? "›"
          : "·";
  const statusLabel =
    hardBlocked
      ? "已阻止"
      : item.status === "failed"
        ? "失败"
        : item.status === "completed"
          ? "完成"
          : "执行中";
  const content = (
    <>
      <span className="activity-copy">
        <span className="activity-heading">
          <strong>{item.title}</strong>
          {item.count && item.count > 1 ? <span className="activity-count">{item.count}</span> : null}
          <i>{statusLabel}</i>
        </span>
        {noteMarkdown !== null && expanded ? null : (
          <span className="activity-summary">{item.summary}</span>
        )}
      </span>
      {item.detail !== undefined ? <ChevronIcon className={expanded ? "is-expanded" : ""} /> : null}
    </>
  );

  return (
    <div
      className={`activity-row kind-${item.activityKind} is-${item.status}${expanded ? " is-expanded" : ""}${hardBlocked ? " is-hard-blocked" : ""}`}
    >
      <span className="activity-status" aria-hidden="true">
        {statusIcon}
      </span>
      {item.detail !== undefined ? (
        <button
          type="button"
          className="activity-main"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {content}
        </button>
      ) : (
        <div className="activity-main">{content}</div>
      )}
      {structured && expanded ? (
        <ol className="activity-steps" aria-label={`${item.title}执行步骤`}>
          {steps.map((step, index) => (
            <li className={`is-${step.status}`} key={`${step.name}:${step.subject}:${index}`}>
              <span className="activity-step-marker" aria-hidden="true">
                {step.status === "completed" ? "✓" : step.status === "failed" ? "!" : "·"}
              </span>
              <span>
                <strong>{step.subject}</strong>
                {step.summary ? <small>{step.summary}</small> : null}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
      {expanded && noteMarkdown !== null ? (
        <div className="activity-note-detail">
          <MarkdownMessage content={noteMarkdown} />
        </div>
      ) : null}
      {detailVisible && item.detail !== undefined ? (
        <StructuredToolDetail detail={item.detail} activityKind={item.activityKind} />
      ) : null}
      {item.approval ? (
        <div className="activity-inline-approval">
          <ApprovalCard
            item={{
              id: `approval:${item.approval.approvalId}`,
              kind: "approval",
              turnId: item.turnId,
              ...item.approval,
            }}
            onApproval={onApproval}
            available={approvalAvailable}
          />
        </div>
      ) : null}
    </div>
  );
}
