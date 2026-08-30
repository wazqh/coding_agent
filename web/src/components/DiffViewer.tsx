import { useEffect, useState } from "react";

import type { ChangeSummary, FilePreviewData } from "../state/store";
import { UnifiedDiff } from "./UnifiedDiff";

interface DiffViewerProps {
  change: ChangeSummary;
  onPreview?: (path: string) => void;
  onUndo?: (changeId: string) => void;
  busy?: boolean;
  previewOpen?: boolean;
  filePreview?: FilePreviewData | null;
}

export function DiffViewer({
  change,
  onPreview,
  onUndo,
  busy = false,
  previewOpen = false,
  filePreview = null,
}: DiffViewerProps) {
  const [undoArmed, setUndoArmed] = useState(false);
  useEffect(() => setUndoArmed(false), [change.id]);

  return (
    <section className="diff-viewer" aria-label={`${change.path} 的变更`}>
      <div className="diff-toolbar">
        <div>
          <span className="mono-label">{change.path}</span>
          <small>
            {previewOpen
              ? filePreview
                ? `文件预览 · ${filePreview.language} · ${filePreview.size.toLocaleString()} B · 只读`
                : "正在读取文件…"
              : `${change.kind === "created" ? "新建文件" : "修改文件"} · Unified Diff`}
          </small>
        </div>
        <div className="diff-toolbar-actions">
          <span className="diff-stats mono-label">
            <b>+{change.additions}</b>
            <i>−{change.deletions}</i>
          </span>
          {onPreview ? (
            <button type="button" onClick={() => onPreview(change.path)}>
              {previewOpen ? "查看 Diff" : "查看文件"}
            </button>
          ) : null}
          {onUndo && change.reversible !== false ? (
            <button
              type="button"
              className={undoArmed ? "diff-undo is-armed" : "diff-undo"}
              disabled={busy}
              onClick={() => {
                if (!undoArmed) {
                  setUndoArmed(true);
                  return;
                }
                onUndo(change.id);
                setUndoArmed(false);
              }}
            >
              {undoArmed ? "确认撤销" : "撤销此变更"}
            </button>
          ) : null}
        </div>
      </div>
      {previewOpen ? (
        <div className="diff-scroll file-content-scroll" data-testid="file-content-scroll">
          {filePreview ? (
            <pre><code>{filePreview.text}</code></pre>
          ) : (
            <div className="file-preview-loading">正在读取文件…</div>
          )}
        </div>
      ) : (
        <UnifiedDiff value={change.diff} />
      )}
    </section>
  );
}
