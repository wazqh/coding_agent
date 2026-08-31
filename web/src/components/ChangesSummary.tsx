import { useEffect, useRef, useState } from "react";

import type { ChangeSummary } from "../state/store";
import { ChevronIcon, FileIcon } from "./icons";

interface ChangesSummaryProps {
  changes: ChangeSummary[];
  selectedId?: string;
  onSelect: (change: ChangeSummary) => void;
  onReviewAll?: (decision: "accept" | "discard") => void;
  busy?: boolean;
}

export function ChangesSummary({
  changes,
  selectedId,
  onSelect,
  onReviewAll,
  busy = false,
}: ChangesSummaryProps) {
  const pendingChanges = changes.filter((item) => item.reviewStatus !== "accepted");
  const previousReviewStates = useRef(
    new Map(changes.map((item) => [item.id, item.reviewStatus] as const)),
  );
  const [acceptedToastCount, setAcceptedToastCount] = useState(0);

  useEffect(() => {
    const previous = previousReviewStates.current;
    const acceptedNow = changes.filter(
      (item) =>
        item.reviewStatus === "accepted" &&
        previous.has(item.id) &&
        previous.get(item.id) !== "accepted",
    ).length;
    previousReviewStates.current = new Map(
      changes.map((item) => [item.id, item.reviewStatus] as const),
    );
    if (acceptedNow) setAcceptedToastCount(acceptedNow);
  }, [changes]);

  useEffect(() => {
    if (!acceptedToastCount) return;
    const timer = window.setTimeout(() => setAcceptedToastCount(0), 1_800);
    return () => window.clearTimeout(timer);
  }, [acceptedToastCount]);

  if (!changes.length) {
    return (
      <div className="drawer-empty">
        <span className="drawer-empty-icon">
          <FileIcon />
        </span>
        <strong>本次运行还没有 Agent 变更</strong>
        <p>新建或修改文件后，Diff 会立即出现在这里。</p>
      </div>
    );
  }

  return (
    <section className="changes-summary" aria-label="变更文件">
      <div className="changes-summary-heading">
        <strong>{pendingChanges.length ? `待审变更 ${pendingChanges.length} 项` : "变更已审阅"}</strong>
        {pendingChanges.length ? (
          <span>
            <b>+{pendingChanges.reduce((total, item) => total + item.additions, 0)}</b>
            <i>−{pendingChanges.reduce((total, item) => total + item.deletions, 0)}</i>
          </span>
        ) : null}
      </div>
      {acceptedToastCount ? (
        <div
          className="change-accepted-toast"
          role="status"
          aria-label={`已接受 ${acceptedToastCount} 项变更`}
        >
          <span aria-hidden="true">✓</span>
          <strong>已接受 {acceptedToastCount} 项变更</strong>
        </div>
      ) : null}
      {onReviewAll && pendingChanges.length ? (
        <div className="change-review-all" role="group" aria-label="批量审阅变更">
          <button type="button" disabled={busy} onClick={() => onReviewAll("accept")}>接受全部</button>
          <button type="button" className="danger-action" disabled={busy || !pendingChanges.some((item) => item.reversible !== false)} onClick={() => onReviewAll("discard")}>全部撤销</button>
        </div>
      ) : null}
      {pendingChanges.length ? <div className="change-list">
        {pendingChanges.map((change) => (
          <button
            key={change.id}
            type="button"
            className={`change-row${change.id === selectedId ? " is-selected" : ""}`}
            aria-label={`${change.path}，新增 ${change.additions} 行，删除 ${change.deletions} 行`}
            aria-expanded={change.id === selectedId}
            onClick={() => onSelect(change)}
          >
            <FileIcon />
            <span className="change-copy">
              <span className="change-path mono-label">{change.path}</span>
              <small>{change.kind === "created" ? "新建" : "修改"}</small>
              {change.reviewStatus === "conflicted" ? <small className="review-state is-conflict">存在冲突</small> : null}
            </span>
            <span className="change-stats mono-label">
              <b>+{change.additions}</b>
              <i>−{change.deletions}</i>
            </span>
            <ChevronIcon />
          </button>
        ))}
      </div> : null}
    </section>
  );
}
