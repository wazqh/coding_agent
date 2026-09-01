import type { CSSProperties } from "react";
import { createPortal } from "react-dom";

import type { TimelineItem } from "../state/store";
import { CloseIcon } from "./icons";
import { StructuredToolDetail } from "./StructuredToolDetail";
import { useConversationPaneBounds } from "./useConversationPaneBounds";

type ActivityItem = Extract<TimelineItem, { kind: "activity" }>;

interface ActivityDetailPaneProps {
  item: ActivityItem;
  drawerWidth: number;
  onClose: () => void;
}

function activityLabel(item: ActivityItem): string {
  return item.activityKind === "validation" ? "验证" : "命令";
}

function statusLabel(item: ActivityItem): string {
  if (item.status === "completed") return item.activityKind === "validation" ? "通过" : "完成";
  if (item.status === "failed") return "失败";
  if (item.status === "running") return "执行中";
  return item.status;
}

export function ActivityDetailPane({ item, drawerWidth, onClose }: ActivityDetailPaneProps) {
  const bounds = useConversationPaneBounds();
  const label = activityLabel(item);
  return createPortal(
    <section
      className={`activity-detail-pane is-${item.status}`}
      role="dialog"
      aria-label={`${label}执行详情`}
      style={{
        "--resource-drawer-width": `${drawerWidth}px`,
        "--resource-content-left": `${bounds.left}px`,
        "--resource-content-top": `${bounds.top}px`,
        "--resource-content-bottom": `${bounds.bottom}px`,
      } as CSSProperties}
    >
      <header>
        <div>
          <strong>{label}详情</strong>
          <small><span className={`activity-detail-status is-${item.status}`}>{statusLabel(item)}</span>{item.summary}</small>
        </div>
        <button type="button" className="icon-button" aria-label="关闭执行详情" onClick={onClose}>
          <CloseIcon />
        </button>
      </header>
      <div className="activity-detail-pane-content">
        {item.detail !== undefined ? (
          <StructuredToolDetail detail={item.detail} activityKind={item.activityKind} />
        ) : (
          <div className="resource-preview-loading" role="status">本条记录没有更多详情</div>
        )}
      </div>
    </section>,
    document.body,
  );
}
