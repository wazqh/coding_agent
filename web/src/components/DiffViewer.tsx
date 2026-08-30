import { Diff, Hunk, parseDiff } from "react-diff-view";
import "react-diff-view/style/index.css";

import type { ChangeSummary } from "../state/store";

interface DiffViewerProps {
  change: ChangeSummary;
  onPreview?: (path: string) => void;
}

export function DiffViewer({ change, onPreview }: DiffViewerProps) {
  const files = parseDiff(change.diff);

  return (
    <section className="diff-viewer" aria-label={`${change.path} 的变更`}>
      <div className="diff-toolbar">
        <div>
          <span className="mono-label">{change.path}</span>
          <small>统一 Diff</small>
        </div>
        <span className="diff-stats mono-label">
          <b>+{change.additions}</b>
          <i>−{change.deletions}</i>
        </span>
        {onPreview ? (
          <button type="button" onClick={() => onPreview(change.path)}>
            查看文件
          </button>
        ) : null}
      </div>
      <div className="diff-scroll" data-testid="diff-scroll">
        {files.length ? (
          files.map((file, index) => (
            <Diff
              key={`${file.oldRevision}-${file.newRevision}-${index}`}
              viewType="unified"
              diffType={file.type}
              hunks={file.hunks}
            >
              {(hunks) => hunks.map((hunk) => <Hunk key={hunk.content} hunk={hunk} />)}
            </Diff>
          ))
        ) : (
          <pre>{change.diff}</pre>
        )}
      </div>
    </section>
  );
}
