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
        <strong>Agent 修改 {changes.length} 处</strong>
        <span>
          <b>+{changes.reduce((total, item) => total + item.additions, 0)}</b>
          <i>−{changes.reduce((total, item) => total + item.deletions, 0)}</i>
        </span>
      </div>
      {onReviewAll ? (
        <div className="change-review-all" role="group" aria-label="批量审阅变更">
          <button type="button" disabled={busy || !changes.some((item) => item.reviewStatus !== "accepted")} onClick={() => onReviewAll("accept")}>接受全部</button>
          <button type="button" className="danger-action" disabled={busy || !changes.some((item) => item.reversible !== false)} onClick={() => onReviewAll("discard")}>放弃全部</button>
        </div>
      ) : null}
      <div className="change-list">
        {changes.map((change) => (
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
              {change.reviewStatus === "accepted" ? <small className="review-state">已接受</small> : null}
              {change.reviewStatus === "conflicted" ? <small className="review-state is-conflict">存在冲突</small> : null}
            </span>
            <span className="change-stats mono-label">
              <b>+{change.additions}</b>
              <i>−{change.deletions}</i>
            </span>
            <ChevronIcon />
          </button>
        ))}
      </div>
    </section>
  );
}
