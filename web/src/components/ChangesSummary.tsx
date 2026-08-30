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
