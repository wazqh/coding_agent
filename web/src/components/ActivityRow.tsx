import { useState } from "react";

import type { TimelineItem } from "../state/store";
import { ChevronIcon } from "./icons";

type Activity = Extract<TimelineItem, { kind: "activity" }>;

interface ActivityStep {
  name: string;
  subject: string;
  status: string;
  summary: string;
}

function activitySteps(detail: unknown): ActivityStep[] {
  if (typeof detail !== "object" || detail === null || !("steps" in detail)) return [];
  const steps = (detail as { steps?: unknown }).steps;
  if (!Array.isArray(steps)) return [];
  return steps.flatMap((step) => {
    if (typeof step !== "object" || step === null) return [];
    const value = step as Record<string, unknown>;
    return [{
      name: typeof value.name === "string" ? value.name : "tool",
      subject: typeof value.subject === "string" ? value.subject : "执行工具",
      status: typeof value.status === "string" ? value.status : "running",
      summary: typeof value.summary === "string" ? value.summary : "",
    }];
  });
}

function rawDetail(detail: unknown): unknown {
  if (typeof detail !== "object" || detail === null || !("raw" in detail)) return detail;
  return (detail as { raw?: unknown }).raw;
}

export function ActivityRow({ item, showRaw = false }: { item: Activity; showRaw?: boolean }) {
  const steps = activitySteps(item.detail);
  const structured = steps.length > 0;
  const [expanded, setExpanded] = useState(structured);
  const detailVisible = showRaw || (!structured && expanded);
  const statusIcon =
    item.status === "failed"
      ? "!"
      : item.status === "completed"
        ? "✓"
        : item.activityKind === "command"
          ? "›"
          : "·";
  const statusLabel =
    item.status === "failed" ? "失败" : item.status === "completed" ? "完成" : "执行中";
  const content = (
    <>
      <span className="activity-copy">
        <span className="activity-heading">
          <strong>{item.title}</strong>
          {item.count && item.count > 1 ? <span className="activity-count">{item.count}</span> : null}
          <i>{statusLabel}</i>
        </span>
        <span className="activity-summary">{item.summary}</span>
      </span>
      {item.detail !== undefined ? <ChevronIcon className={expanded ? "is-expanded" : ""} /> : null}
    </>
  );

  return (
    <div className={`activity-row kind-${item.activityKind} is-${item.status}`}>
      <span className="activity-status" aria-hidden="true">
        {statusIcon}
      </span>
      {item.detail !== undefined ? (
        <button
          type="button"
          className="activity-main"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {content}
        </button>
      ) : (
        <div className="activity-main">{content}</div>
      )}
      {structured && expanded ? (
        <ol className="activity-steps" aria-label={`${item.title}执行步骤`}>
          {steps.map((step, index) => (
            <li className={`is-${step.status}`} key={`${step.name}:${step.subject}:${index}`}>
              <span className="activity-step-marker" aria-hidden="true">
                {step.status === "completed" ? "✓" : step.status === "failed" ? "!" : "·"}
              </span>
              <span>
                <strong>{step.subject}</strong>
                {step.summary ? <small>{step.summary}</small> : null}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
      {detailVisible && item.detail !== undefined ? (
        <pre className="activity-detail">{JSON.stringify(rawDetail(item.detail), null, 2)}</pre>
      ) : null}
    </div>
  );
}
