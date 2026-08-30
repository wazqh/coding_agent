import { useEffect, useState } from "react";
import type { ApprovalDecision } from "../protocol/types";
import type { TimelineItem } from "../state/store";
import { UnifiedDiff } from "./UnifiedDiff";

type Approval = Extract<TimelineItem, { kind: "approval" }>;

interface ApprovalCardProps {
  item: Approval;
  onApproval: (approvalId: string, decision: ApprovalDecision) => boolean;
  available?: boolean;
}

export function ApprovalCard({ item, onApproval, available = true }: ApprovalCardProps) {
  const [pending, setPending] = useState<ApprovalDecision | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);
  useEffect(() => {
    if (!available) setPending(null);
  }, [available]);
  const resolve = (decision: ApprovalDecision) => {
    if (pending) return;
    if (onApproval(item.approvalId, decision)) setPending(decision);
  };
  const resolvedLabel = (() => {
    if (!item.resolved) return "需要批准";
    if (item.decision === "allow_once") return "已允许一次";
    if (item.decision === "allow_session") return "本会话已允许";
    if (item.decision === "deny") return "已拒绝";
    if (item.decision === "cancelled") return "已取消";
    return "审批已结束";
  })();
  return (
    <section
      className={`approval-card${item.resolved ? " is-resolved" : ""}${item.decision === "deny" ? " is-denied" : ""}`}
    >
      <div className="approval-heading">
        <span className="approval-dot" />
        <div>
          <span>{resolvedLabel}</span>
          <strong>{item.action === "run_command" ? "运行命令" : item.action}</strong>
        </div>
      </div>
      <code>{item.subject}</code>
      <p>{item.summary}</p>
      {item.diff ? (
        <div className="approval-diff">
          <button
            type="button"
            className="approval-diff-toggle"
            aria-expanded={diffOpen}
            onClick={() => setDiffOpen((value) => !value)}
          >
            {diffOpen ? "收起拟议变更" : "查看拟议变更"}
          </button>
          {diffOpen ? <UnifiedDiff value={item.diff} className="approval-diff-content" /> : null}
        </div>
      ) : null}
      {!item.resolved ? (
        <div className="approval-actions">
          <button
            type="button"
            disabled={!available || pending !== null}
            onClick={() => resolve("allow_once")}
          >
            允许一次
          </button>
          <button
            type="button"
            disabled={!available || pending !== null}
            onClick={() => resolve("allow_session")}
          >
            本会话允许
          </button>
          <button
            className="deny-button"
            type="button"
            disabled={!available || pending !== null}
            onClick={() => resolve("deny")}
          >
            {pending ? "处理中…" : "拒绝"}
          </button>
        </div>
      ) : null}
    </section>
  );
}
