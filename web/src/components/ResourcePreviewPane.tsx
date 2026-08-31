import type { CSSProperties } from "react";
import { createPortal } from "react-dom";

import type { FilePreviewData } from "../state/store";
import { FilePreview } from "./FilePreview";
import { CloseIcon } from "./icons";
import { useConversationPaneBounds } from "./useConversationPaneBounds";

interface ResourcePreviewPaneProps {
  path: string;
  drawerWidth: number;
  file: FilePreviewData | null;
  onClose: () => void;
}

export function ResourcePreviewPane({ path, drawerWidth, file, onClose }: ResourcePreviewPaneProps) {
  const ready = file?.path.replaceAll("\\", "/") === path;
  const bounds = useConversationPaneBounds();
  return createPortal(
    <section
      className="resource-preview-pane"
      role="dialog"
      aria-label={`${path} 文件预览`}
      style={{
        "--resource-drawer-width": `${drawerWidth}px`,
        "--resource-content-left": `${bounds.left}px`,
        "--resource-content-top": `${bounds.top}px`,
        "--resource-content-bottom": `${bounds.bottom}px`,
      } as CSSProperties}
    >
      <header>
        <div><strong className="mono-label">{path}</strong><small>工作区只读预览</small></div>
        <button type="button" className="icon-button" aria-label="关闭文件预览" onClick={onClose}>
          <CloseIcon />
        </button>
      </header>
      <div className="resource-preview-pane-content">
        {ready && file ? (
          <FilePreview file={file} />
        ) : (
          <div className="resource-preview-loading" role="status">正在读取 {path}…</div>
        )}
      </div>
    </section>,
    document.body,
  );
}
