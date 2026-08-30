import { useState } from "react";
import type { TimelineItem } from "../state/store";
import { StructuredToolDetail } from "./StructuredToolDetail";

type Validation = Extract<TimelineItem, { kind: "activity" }>;

export function ValidationCard({ item }: { item: Validation }) {
  const [expanded, setExpanded] = useState(false);
  const passed = item.status === "completed";
  const running = item.status === "running";
  const hasDetail = item.detail !== undefined && item.detail !== null;
  return (
    <section className={`validation-card is-${item.status}`}>
      <span className="validation-icon" aria-hidden="true">
        {running ? "·" : passed ? "✓" : "!"}
      </span>
      <div>
        <strong>{running ? "正在验证" : passed ? "验证通过" : "验证失败"}</strong>
        <span>{item.summary || item.title}</span>
      </div>
      {!passed && !running && hasDetail ? (
        <>
          <button type="button" onClick={() => setExpanded((value) => !value)}>
            {expanded ? "收起失败输出" : "展开失败输出"}
          </button>
          {expanded ? <StructuredToolDetail detail={item.detail} activityKind="validation" /> : null}
        </>
      ) : null}
    </section>
  );
}
