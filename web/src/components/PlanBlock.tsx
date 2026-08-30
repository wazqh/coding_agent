import { useEffect, useState } from "react";

import { ChevronIcon } from "./icons";

interface PlanBlockProps {
  steps: Array<Record<string, unknown>>;
  active?: boolean;
}

function stepLabel(step: Record<string, unknown>): string {
  return String(step.step ?? "未命名步骤").replace(/^\s*\d+\s*[.)、．]\s*/, "");
}

export function PlanBlock({ steps, active = false }: PlanBlockProps) {
  const statusSignature = steps.map((step) => String(step.status)).join("|");
  const completed = steps.filter((step) => step.status === "completed").length;
  const complete = completed === steps.length && steps.length > 0;
  const [expanded, setExpanded] = useState(active || !complete);
  const current =
    steps.find((step) => step.status === "in_progress") ??
    steps.find((step) => step.status !== "completed") ??
    steps.at(-1);
  const currentIndex = Math.max(0, steps.indexOf(current ?? steps[0]));
  const currentLabel = current ? stepLabel(current) : "等待 Agent 更新计划";
  const title = complete ? "计划已完成" : active ? "正在按计划执行" : "计划未闭环";
  const detail = complete
    ? `共 ${steps.length} 步`
    : active
      ? `第 ${currentIndex + 1}/${steps.length} 步 · ${currentLabel}`
      : completed > 0 || current?.status === "in_progress"
        ? `已完成 ${completed}/${steps.length} 步 · 停在：${currentLabel}`
        : `共 ${steps.length} 步 · 尚未开始`;

  useEffect(() => {
    if (steps.length > 0) setExpanded(active || !complete);
  }, [active, complete, statusSignature, steps.length]);

  return (
    <section className={`plan-block ${active ? "is-active" : "is-history"}`}>
      <button
        type="button"
        className="plan-summary"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="plan-progress" aria-hidden="true">
          <i style={{ width: `${steps.length ? (completed * 100) / steps.length : 0}%` }} />
        </span>
        <div>
          <strong>{title}</strong>
          <small>{detail}</small>
        </div>
        <span className="plan-count mono-label">{completed}/{steps.length}</span>
        <ChevronIcon className={expanded ? "is-expanded" : ""} />
      </button>
      {expanded ? (
        <ol>
          {steps.map((step, index) => {
            const status = String(step.status ?? "pending");
            return (
              <li
                className={`is-${status}`}
                aria-current={active && status === "in_progress" ? "step" : undefined}
                key={`${stepLabel(step)}-${index}`}
              >
                <span>{status === "completed" ? "✓" : index + 1}</span>
                <p>{stepLabel(step)}</p>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
