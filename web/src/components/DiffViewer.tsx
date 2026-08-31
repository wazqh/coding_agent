import { useState } from "react";

import type { ChangeSummary, FilePreviewData } from "../state/store";
import { UnifiedDiff } from "./UnifiedDiff";
import { SideBySideDiff } from "./SideBySideDiff";
import { CloseIcon } from "./icons";

interface DiffViewerProps {
  change: ChangeSummary;
  onPreview?: (path: string) => void;
  onReview?: (changeId: string, decision: "accept" | "discard") => void;
  onClose?: () => void;
  busy?: boolean;
  previewOpen?: boolean;
  filePreview?: FilePreviewData | null;
  allowEnlarge?: boolean;
}

export function DiffViewer({
  change,
  onPreview,
  onReview,
  onClose,
  busy = false,
  previewOpen = false,
  filePreview = null,
  allowEnlarge = true,
}: DiffViewerProps) {
  const [mode, setMode] = useState<"unified" | "split">("unified");
  const [enlarged, setEnlarged] = useState(false);

  return (
    <section className={`diff-viewer${enlarged ? " is-enlarged" : ""}`} aria-label={`${change.path} 的变更`}>
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
          {!previewOpen ? (
            <div className="diff-mode" role="group" aria-label="Diff 布局">
              <button type="button" className={mode === "unified" ? "is-active" : ""} onClick={() => setMode("unified")}>统一视图</button>
              <button type="button" className={mode === "split" ? "is-active" : ""} onClick={() => setMode("split")}>并排对比</button>
            </div>
          ) : null}
          {allowEnlarge ? (
            <button type="button" onClick={() => setEnlarged((value) => !value)}>
              {enlarged ? "退出放大" : "放大审查"}
            </button>
          ) : null}
          {onPreview ? (
            <button type="button" onClick={() => onPreview(change.path)}>
              {previewOpen ? "查看 Diff" : "查看文件"}
            </button>
          ) : null}
          {onReview ? (
            <>
              <button type="button" disabled={busy || change.reviewStatus === "accepted"} onClick={() => onReview(change.id, "accept")}>接受改动</button>
              <button type="button" className="diff-undo" disabled={busy || change.reversible === false} onClick={() => onReview(change.id, "discard")}>撤销改动</button>
            </>
          ) : null}
          {onClose ? (
            <button type="button" className="icon-button diff-close" aria-label="关闭变更审查" onClick={onClose}>
              <CloseIcon />
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
        mode === "split" ? <SideBySideDiff value={change.diff} /> : <UnifiedDiff value={change.diff} />
      )}
    </section>
  );
}
