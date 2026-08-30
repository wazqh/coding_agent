import type { ChangeSummary } from "../state/store";
import { ChevronIcon, FileIcon } from "./icons";

interface ChangesSummaryProps {
  changes: ChangeSummary[];
  selectedId?: string;
  onSelect: (change: ChangeSummary) => void;
}

export function ChangesSummary({ changes, selectedId, onSelect }: ChangesSummaryProps) {
  if (!changes.length) {
    return (
      <div className="drawer-empty">
        <span className="drawer-empty-icon">
          <FileIcon />
        </span>
        <strong>暂时没有文件变更</strong>
        <p>Agent 修改工作区后，可在这里逐文件审阅 Diff。</p>
      </div>
    );
  }

  return (
    <section className="changes-summary" aria-label="变更文件">
      <div className="changes-summary-heading">
        <strong>已记录 {changes.length} 次改动</strong>
        <span>
          <b>+{changes.reduce((total, item) => total + item.additions, 0)}</b>
          <i>−{changes.reduce((total, item) => total + item.deletions, 0)}</i>
        </span>
      </div>
      <div className="change-list">
        {changes.map((change) => (
          <button
            key={change.id}
            type="button"
            className={`change-row${change.id === selectedId ? " is-selected" : ""}`}
            aria-label={`${change.path}，新增 ${change.additions} 行，删除 ${change.deletions} 行`}
            onClick={() => onSelect(change)}
          >
            <FileIcon />
            <span className="change-path mono-label">{change.path}</span>
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
