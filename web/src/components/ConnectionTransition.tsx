import { useEffect, useState } from "react";

import type { ConnectionState } from "../protocol/types";

interface ConnectionTransitionProps {
  state: ConnectionState;
  ready: boolean;
  error: string;
  activity?: "startup" | "model-restart" | "workspace-restart";
  onRetry?: () => void;
  onOpenSettings?: () => void;
}

export function ConnectionTransition({
  state,
  ready,
  error,
  activity = "startup",
  onRetry = () => undefined,
  onOpenSettings = () => undefined,
}: ConnectionTransitionProps) {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (ready || error) {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), 8_000);
    return () => window.clearTimeout(timer);
  }, [error, ready, state]);

  if (ready) return null;

  const failed = Boolean(error) || state === "error";
  const title = failed
    ? "无法连接本地 Agent"
    : activity === "model-restart"
      ? "正在应用模型配置"
      : activity === "workspace-restart"
        ? "正在切换项目"
      : state === "connected"
        ? "正在恢复工作区"
        : "正在启动本地 Agent";
  const description = failed
    ? error || "本地运行时没有响应"
    : activity === "model-restart"
      ? "正在重启本地 Agent 并恢复当前会话…"
      : activity === "workspace-restart"
        ? "正在加载工作区资源并恢复该项目最近使用的会话…"
      : state === "connected"
        ? "正在加载项目资源与最近会话…"
        : "正在建立仅限本机的安全连接…";

  return (
    <div
      className={`connection-transition${failed ? " is-error" : ""}`}
      role={failed ? "alert" : "status"}
      aria-label={title}
      aria-busy={failed ? undefined : true}
    >
      <div className="connection-transition-card">
        <span className="connection-kicker" aria-hidden="true">
          <i /> Local Agent
        </span>
        <strong>{title}</strong>
        <p>{description}</p>
        {!failed ? (
          <span className="connection-orbit" aria-hidden="true">
            <i /><i /><i />
          </span>
        ) : null}
        {!failed && slow ? (
          <small>启动可能需要更长时间，请保持当前窗口打开。</small>
        ) : null}
        {failed ? (
          <div className="connection-actions">
            <button type="button" className="primary-small" onClick={onRetry}>重新连接</button>
            <button type="button" onClick={onOpenSettings}>检查模型设置</button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
