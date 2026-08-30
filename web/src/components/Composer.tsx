import { useEffect, useRef, useState } from "react";

import { ArrowUpIcon, StopIcon } from "./icons";
import type { CompletionState } from "../state/store";

interface ComposerProps {
  busy: boolean;
  ready?: boolean;
  modelName: string;
  permissions: "prompt" | "auto" | "read-only";
  contextPercent?: number;
  completion?: CompletionState | null;
  onCompletionQuery?: (text: string, cursor: number) => void;
  onOpenModel?: () => void;
  onOpenPermissions?: () => void;
  onOpenContext?: () => void;
  onSend?: (task: string) => boolean | void;
  onStop?: () => void;
}

const permissionLabels = {
  prompt: "询问",
  auto: "自动",
  "read-only": "只读",
};

export function Composer({
  busy,
  ready = true,
  modelName,
  permissions,
  contextPercent,
  completion = null,
  onCompletionQuery = () => undefined,
  onOpenModel = () => undefined,
  onOpenPermissions = () => undefined,
  onOpenContext = () => undefined,
  onSend = () => undefined,
  onStop = () => undefined,
}: ComposerProps) {
  const [task, setTask] = useState("");
  const [cursor, setCursor] = useState(0);
  const [selectedCompletion, setSelectedCompletion] = useState(0);
  const [dismissedAt, setDismissedAt] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const completionKey = `${task}\0${cursor}`;
  const visibleItems =
    completion?.text === task && completion.cursor === cursor && dismissedAt !== completionKey
      ? completion.items
      : [];

  useEffect(() => {
    const before = task.slice(0, cursor);
    const shouldQuery =
      /(?:^|\s)[/@$][^\s]*$/.test(before) ||
      /^\/(?:model|steps|permissions|memory|skills|raw)\s/.test(before);
    if (!shouldQuery) return;
    const timer = window.setTimeout(() => onCompletionQuery(task, cursor), 70);
    return () => window.clearTimeout(timer);
  }, [cursor, onCompletionQuery, task]);

  useEffect(() => setSelectedCompletion(0), [completion?.cursor, completion?.text]);

  useEffect(() => {
    if (!visibleItems.length) return;
    if (selectedCompletion >= visibleItems.length) {
      setSelectedCompletion(visibleItems.length - 1);
      return;
    }
    optionRefs.current[selectedCompletion]?.scrollIntoView({ block: "nearest" });
  }, [selectedCompletion, visibleItems.length]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 154)}px`;
  }, [task]);

  const applyCompletion = (index: number) => {
    const item = visibleItems[index];
    if (!item) return;
    const suffix = item.kind === "file" || item.kind === "skill" ? " " : "";
    const value = `${task.slice(0, item.replace_start)}${item.insert_text}${suffix}${task.slice(item.replace_end)}`;
    const nextCursor = item.replace_start + item.insert_text.length + suffix.length;
    setTask(value);
    setCursor(nextCursor);
    setDismissedAt("");
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(nextCursor, nextCursor);
    });
  };

  const submit = () => {
    const value = task.trim();
    if (busy || !ready || !value) return;
    if (onSend(value) !== false) setTask("");
  };

  return (
    <div className="composer-dock">
      {!ready ? (
        <div className="runtime-strip" aria-live="polite">
          <span className="status-pulse" />
          <strong>正在连接</strong>
        </div>
      ) : null}
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <textarea
          ref={textareaRef}
          aria-label="任务输入"
          placeholder="继续追问，或描述一个新的编程任务…"
          rows={1}
          value={task}
          disabled={busy || !ready}
          onChange={(event) => {
            setTask(event.target.value);
            setCursor(event.target.selectionStart);
            setDismissedAt("");
          }}
          onClick={(event) => setCursor(event.currentTarget.selectionStart)}
          onSelect={(event) => setCursor(event.currentTarget.selectionStart)}
          onKeyDown={(event) => {
            if (visibleItems.length && event.key === "ArrowDown") {
              event.preventDefault();
              setSelectedCompletion((value) => (value + 1) % visibleItems.length);
              return;
            }
            if (visibleItems.length && event.key === "ArrowUp") {
              event.preventDefault();
              setSelectedCompletion((value) => (value - 1 + visibleItems.length) % visibleItems.length);
              return;
            }
            if (visibleItems.length && event.key === "Tab") {
              event.preventDefault();
              applyCompletion(selectedCompletion);
              return;
            }
            if (event.key === "Enter" && !event.shiftKey) {
              const item = visibleItems[selectedCompletion];
              const current = item ? task.slice(item.replace_start, item.replace_end) : "";
              if (item && current !== item.insert_text) {
                event.preventDefault();
                applyCompletion(selectedCompletion);
                return;
              }
              event.preventDefault();
              submit();
            }
            if (event.key === "Escape" && visibleItems.length) {
              event.preventDefault();
              setDismissedAt(completionKey);
            } else if (event.key === "Escape" && busy) onStop();
          }}
        />
        {visibleItems.length ? (
          <div className="completion-popover" role="listbox" aria-label="输入补全">
            {visibleItems.map((item, index) => (
              <button
                key={`${item.kind}:${item.label}`}
                ref={(node) => {
                  optionRefs.current[index] = node;
                }}
                type="button"
                role="option"
                aria-selected={index === selectedCompletion}
                className={index === selectedCompletion ? "is-selected" : ""}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => applyCompletion(index)}
              >
                <span className={`completion-kind is-${item.kind}`}>{item.kind === "command" ? "/" : item.kind === "file" ? "@" : item.kind === "skill" ? "$" : "·"}</span>
                <strong className="mono-label">{item.label}</strong>
                <small>{item.description}</small>
              </button>
            ))}
          </div>
        ) : null}
        <div className="composer-toolbar">
          <div className="composer-options">
            {contextPercent !== undefined ? (
              <button type="button" className="context-meter" onClick={onOpenContext}>上下文 {contextPercent}%</button>
            ) : null}
            <button type="button" className="option-button mono-label" onClick={onOpenModel}>{modelName}</button>
            <button type="button" className="option-button" onClick={onOpenPermissions}>{permissionLabels[permissions]}</button>
          </div>
          <button
            type={busy ? "button" : "submit"}
            className={`send-button${busy ? " is-stop" : ""}`}
            aria-label={busy ? "停止任务" : "发送任务"}
            onClick={busy ? onStop : undefined}
            disabled={!busy && (!ready || !task.trim())}
          >
            {busy ? <StopIcon /> : <ArrowUpIcon />}
          </button>
        </div>
      </form>
    </div>
  );
}
