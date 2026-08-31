import type { CSSProperties } from "react";
import { createPortal } from "react-dom";

import type { ChangeSummary } from "../state/store";
import { DiffViewer } from "./DiffViewer";
import { useConversationPaneBounds } from "./useConversationPaneBounds";

interface ChangeReviewPaneProps {
  change: ChangeSummary;
  drawerWidth: number;
  busy?: boolean;
  onReview: (changeId: string, decision: "accept" | "discard") => void;
  onClose: () => void;
}

export function ChangeReviewPane({
  change,
  drawerWidth,
  busy = false,
  onReview,
  onClose,
}: ChangeReviewPaneProps) {
  const bounds = useConversationPaneBounds();
  return createPortal(
    <section
      className="change-review-pane"
      role="dialog"
      aria-label={`${change.path} 变更审查`}
      style={{
        "--resource-drawer-width": `${drawerWidth}px`,
        "--resource-content-left": `${bounds.left}px`,
        "--resource-content-top": `${bounds.top}px`,
        "--resource-content-bottom": `${bounds.bottom}px`,
      } as CSSProperties}
    >
      <DiffViewer
        change={change}
        onReview={onReview}
        onClose={onClose}
        allowEnlarge={false}
        busy={busy}
      />
    </section>,
    document.body,
  );
}
