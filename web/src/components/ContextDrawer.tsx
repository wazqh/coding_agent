import { useEffect, useMemo, useState, type CSSProperties } from "react";

import type {
  ChangeSummary,
  FilePreviewData,
  MemoryState,
  ModelCatalogState,
  RuntimeState,
  SkillsState,
  TimelineItem,
} from "../state/store";
import { ChangesSummary } from "./ChangesSummary";
import { DiffViewer } from "./DiffViewer";
import { FilePreview } from "./FilePreview";
import { CloseIcon } from "./icons";
import { ModelManager, type ModelSetupInput } from "./ModelManager";
import { ResourceFileTree, type ResourceFileStatus } from "./ResourceFileTree";
import { StructuredToolDetail } from "./StructuredToolDetail";

export type InspectorTab = "changes" | "run" | "settings" | "resources" | "context";

interface ContextDrawerProps {
  width: number;
  onWidthChange: (width: number) => void;
  onClose: () => void;
  changes: ChangeSummary[];
  filePreview: FilePreviewData | null;
  onPreview: (path: string) => void;
  onUndoChange: (changeId: string) => void;
  onReviewChange: (changeId: string, decision: "accept" | "discard") => void;
  onReviewAll: (decision: "accept" | "discard") => void;
  timelineItems: TimelineItem[];
  busy: boolean;
  modelName: string;
  permissions: "prompt" | "auto" | "read-only";
  contextPercent?: number;
  runtime: RuntimeState | null;
  modelCatalog: ModelCatalogState | null;
  memoryState: MemoryState | null;
  skillsState: SkillsState | null;
  initialTab?: InspectorTab;
  openModelManager?: boolean;
  onTabChange?: (tab: InspectorTab) => void;
  onRuntimeRefresh: () => void;
  onModelList: () => void;
  onModelSelect: (provider: string, modelId: string) => void;
  onModelReload: () => void;
  onModelProviderConfigure: (
    input: ModelSetupInput,
  ) => Promise<{ persisted: boolean; backend: string }>;
  onPermissionChange: (mode: "prompt" | "auto" | "read-only") => void;
  onStepsChange: (value: number) => boolean | void;
  onStepsReset: () => boolean | void;
  onVerificationChange: (commands: string[]) => boolean | void;
  onMemoryList: () => void;
  onMemoryToggle: (enabled: boolean) => void;
  onRemember: (content: string) => void;
  onForget: (id: string) => void;
  onMemoryClear: () => void;
  onSkillsList: () => void;
  onSkillToggle: (name: string, enabled: boolean) => void;
  onSkillsReload: () => void;
  onCompact: () => void;
}

const tabLabels: Record<InspectorTab, string> = {
  changes: "变更",
  run: "运行",
  settings: "设置",
  resources: "资源",
  context: "上下文",
};

function valueText(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function valueBool(value: unknown): boolean {
  return value === true;
}

export function ContextDrawer(props: ContextDrawerProps) {
  const {
    onClose,
    changes,
    filePreview,
    onPreview,
    busy,
    modelName,
    permissions,
    contextPercent,
    runtime,
    modelCatalog,
    memoryState,
    skillsState,
    initialTab = "changes",
  } = props;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [tab, setTab] = useState<InspectorTab>(initialTab);
  const [resourceTab, setResourceTab] = useState<"files" | "skills" | "memory">("files");
  const [resourcePreviewPath, setResourcePreviewPath] = useState<string | null>(null);
  const [skillQuery, setSkillQuery] = useState("");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [clearArmed, setClearArmed] = useState(false);
  const [stepDraft, setStepDraft] = useState(String(runtime?.steps?.current ?? 24));
  const [pendingStepAction, setPendingStepAction] = useState<
    { kind: "set"; value: number } | { kind: "reset" } | null
  >(null);
  const [stepFeedback, setStepFeedback] = useState<
    { state: "idle" | "saving" | "saved" | "error"; message: string }
  >({ state: "idle", message: "" });
  const [verificationDraft, setVerificationDraft] = useState(
    (runtime?.verification?.commands ?? []).join("\n"),
  );
  const [verificationPending, setVerificationPending] = useState<string | null>(null);
  const [verificationFeedback, setVerificationFeedback] = useState("");
  const [modelManagerOpen, setModelManagerOpen] = useState(props.openModelManager ?? false);
  const selected = changes.find((change) => change.id === selectedId);
  const runItems = props.timelineItems.filter(
    (item): item is Extract<TimelineItem, { kind: "activity" }> =>
      item.kind === "activity" && ["command", "validation"].includes(item.activityKind),
  );
  const resourcePaths = useMemo(() => {
    const paths = new Set(changes.map((change) => change.path));
    const visit = (value: unknown, key = "") => {
      if (typeof value === "string" && ["path", "file"].includes(key) && value.length < 4096) {
        paths.add(value);
      } else if (Array.isArray(value)) {
        value.forEach((item) => visit(item, key));
      } else if (typeof value === "object" && value !== null) {
        Object.entries(value).forEach(([childKey, item]) => visit(item, childKey));
      }
    };
    props.timelineItems.forEach((item) => {
      if (item.kind === "activity") visit(item.detail);
    });
    return [...paths].sort((left, right) => left.localeCompare(right));
  }, [changes, props.timelineItems]);
  const resourceStatuses = useMemo(() => {
    const statuses = new Map<string, ResourceFileStatus>();
    resourcePaths.forEach((path) => statuses.set(path.replaceAll("\\", "/"), "read"));
    changes.forEach((change) => {
      statuses.set(change.path.replaceAll("\\", "/"), change.kind === "created" ? "created" : "modified");
    });
    return statuses;
  }, [changes, resourcePaths]);

  useEffect(() => {
    if (props.openModelManager) setModelManagerOpen(true);
  }, [props.openModelManager]);

  useEffect(() => {
    if (tab === "run" || tab === "settings") {
      props.onRuntimeRefresh();
    }
    if (tab === "settings") {
      props.onModelList();
    } else if (tab === "resources") {
      props.onSkillsList();
      props.onMemoryList();
    }
  }, [tab]);

  useEffect(() => {
    setStepDraft(String(runtime?.steps?.current ?? 24));
  }, [runtime?.steps?.current]);

  useEffect(() => {
    const current = (runtime?.verification?.commands ?? []).join("\n");
    setVerificationDraft(current);
    if (verificationPending !== null && verificationPending === current) {
      setVerificationPending(null);
      setVerificationFeedback("验证规则已保存，下一次文件变更后生效");
    }
  }, [runtime?.verification?.commands]);

  useEffect(() => {
    if (verificationPending === null) return;
    const timer = window.setTimeout(() => {
      setVerificationPending(null);
      setVerificationFeedback("未收到运行时确认，请重试");
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [verificationPending]);

  useEffect(() => {
    if (!pendingStepAction) return;
    const confirmed = pendingStepAction.kind === "set"
      ? runtime?.steps?.current === pendingStepAction.value
      : runtime?.steps?.overridden === false;
    if (!confirmed) return;
    setPendingStepAction(null);
    setStepFeedback({ state: "saved", message: "已保存，下一轮任务生效" });
  }, [pendingStepAction, runtime?.steps?.current, runtime?.steps?.overridden]);

  useEffect(() => {
    if (!pendingStepAction) return;
    const timer = window.setTimeout(() => {
      setPendingStepAction(null);
      setStepFeedback({ state: "error", message: "未收到运行时确认，请重试" });
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [pendingStepAction]);

  useEffect(() => {
    if (selectedId !== null && !changes.some((change) => change.id === selectedId)) {
      setSelectedId(null);
      setPreviewPath(null);
    }
  }, [changes, selectedId]);

  const skillItems = useMemo(() => {
    const items = skillsState?.items ?? [];
    const query = skillQuery.trim().toLocaleLowerCase();
    if (!query) return items;
    return items.filter((item) =>
      `${valueText(item.name)} ${valueText(item.description)} ${valueText(item.source)}`
        .toLocaleLowerCase()
        .includes(query),
    );
  }, [skillQuery, skillsState?.items]);

  const modelValue = `${modelCatalog?.active?.provider ?? ""}\0${modelCatalog?.active?.id ?? modelName}`;
  const stepMinimum = runtime?.steps?.minimum ?? 12;
  const stepMaximum = runtime?.steps?.maximum ?? 100;

  return (
    <aside className="context-drawer" aria-label="任务检查器">
      <div
        className="drawer-resize-handle"
        role="separator"
        aria-label="调整检查器宽度"
        aria-orientation="vertical"
        aria-valuenow={props.width}
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
          const delta = event.key === "ArrowLeft" ? 20 : -20;
          props.onWidthChange(Math.max(360, Math.min(900, props.width + delta)));
        }}
        onPointerDown={(event) => {
          const startX = event.clientX;
          const startWidth = props.width;
          const move = (pointerEvent: PointerEvent) => {
            const viewportLimit = Math.max(360, Math.min(900, window.innerWidth * 0.7));
            props.onWidthChange(
              Math.round(Math.max(360, Math.min(viewportLimit, startWidth + startX - pointerEvent.clientX))),
            );
          };
          const stop = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", stop);
          };
          window.addEventListener("pointermove", move);
          window.addEventListener("pointerup", stop, { once: true });
        }}
      />
      <div className="drawer-header">
        <div>
          <span className="drawer-eyebrow">任务检查器</span>
          <h2>{tabLabels[tab]}</h2>
        </div>
        <button type="button" className="icon-button" aria-label="关闭检查器" onClick={onClose}>
          <CloseIcon />
        </button>
      </div>
      <div className="inspector-tabs" role="tablist" aria-label="检查器面板">
        {(Object.keys(tabLabels) as InspectorTab[]).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? "is-active" : ""}
            onClick={() => {
              setTab(value);
              props.onTabChange?.(value);
            }}
          >
            {tabLabels[value]}
            {value === "changes" && changes.length ? ` ${changes.length}` : ""}
          </button>
        ))}
      </div>
      <div className="drawer-content">
        {tab === "changes" ? (
          <>
            <ChangesSummary
              changes={changes}
              selectedId={selected?.id}
              onSelect={(change) => {
                setSelectedId((current) => (current === change.id ? null : change.id));
                setPreviewPath(null);
              }}
              onReviewAll={props.onReviewAll}
              busy={busy}
            />
            {selected ? (
              <DiffViewer
                change={selected}
                onPreview={(path) => {
                  if (previewPath === path) {
                    setPreviewPath(null);
                    return;
                  }
                  setPreviewPath(path);
                  onPreview(path);
                }}
                onUndo={props.onUndoChange}
                onReview={props.onReviewChange}
                busy={busy}
                previewOpen={previewPath === selected.path}
                filePreview={
                  filePreview && filePreview.path === selected.path ? filePreview : null
                }
              />
            ) : null}
          </>
        ) : null}

        {tab === "run" || tab === "settings" ? (
          <div className="inspector-overview inspector-stack">
            {tab === "run" ? (
              <>
            <section className="settings-card inspector-run-history" aria-label="命令与验证记录">
              <div className="settings-card-heading"><div><strong>执行记录</strong><small>命令、退出状态与结构化结果</small></div></div>
              {runItems.length ? runItems.map((item) => (
                <details key={item.id} className={`run-history-row is-${item.status}`}>
                  <summary><span>{item.activityKind === "validation" ? "验证" : "命令"}</span><strong>{item.summary}</strong><i>{item.status === "completed" ? "完成" : item.status === "failed" ? "失败" : "执行中"}</i></summary>
                  {item.detail !== undefined ? <StructuredToolDetail detail={item.detail} activityKind={item.activityKind} /> : null}
                </details>
              )) : <div className="resource-empty">当前会话还没有命令记录</div>}
            </section>
            <div className="inspector-status-card">
              <span className={busy ? "status-pulse" : "health-dot"} />
              <div>
                <strong>{busy ? "正在执行任务" : "运行时已就绪"}</strong>
                <small>{busy ? "运行期间设置保持只读" : "所有设置仅作用于当前工作区或进程"}</small>
              </div>
            </div>
              </>
            ) : null}

            {tab === "settings" ? (
              <>
            <section className="settings-card" aria-labelledby="model-setting-title">
              <div className="settings-card-heading">
                <div><strong id="model-setting-title">模型</strong><small>OpenAI-compatible 服务商与模型</small></div>
                <div className="settings-card-actions">
                  <button type="button" className="text-action" disabled={busy} onClick={props.onModelReload}>重新加载</button>
                  <button type="button" className={modelManagerOpen ? "text-action" : "primary-small"} disabled={busy} onClick={() => setModelManagerOpen((value) => !value)}>
                    {modelManagerOpen ? "收起" : "添加服务商"}
                  </button>
                </div>
              </div>
              <select
                aria-label="当前模型"
                className="settings-select mono-label"
                value={modelValue}
                disabled={busy || !modelCatalog?.providers?.length}
                onChange={(event) => {
                  const [provider, modelId] = event.target.value.split("\0");
                  props.onModelSelect(provider, modelId);
                }}
              >
                {!modelCatalog?.providers?.length ? <option value={modelValue}>{modelName}</option> : null}
                {modelCatalog?.providers?.flatMap((provider) =>
                  (provider.models ?? [provider.default_model ?? ""]).filter(Boolean).map((model) => (
                    <option key={`${provider.name}:${model}`} value={`${provider.name}\0${model}`}>
                      {provider.name} · {model}
                    </option>
                  )),
                )}
              </select>
              {modelManagerOpen ? (
                <ModelManager busy={busy} onConfigure={props.onModelProviderConfigure} />
              ) : null}
            </section>

            <section className="settings-card" aria-labelledby="permission-setting-title">
              <div className="settings-card-heading">
                <div><strong id="permission-setting-title">权限</strong><small>切换会撤销已有会话授权</small></div>
              </div>
              <div className="segmented-control" role="group" aria-label="权限模式">
                {(["prompt", "auto", "read-only"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    disabled={busy}
                    className={permissions === mode ? "is-active" : ""}
                    onClick={() => props.onPermissionChange(mode)}
                  >
                    {mode === "prompt" ? "询问" : mode === "auto" ? "自动" : "只读"}
                  </button>
                ))}
              </div>
            </section>

            <section className="settings-card" aria-labelledby="steps-setting-title">
              <div className="settings-card-heading">
                <div><strong id="steps-setting-title">最大步骤</strong><small>下一轮任务开始生效，范围 {stepMinimum}–{stepMaximum}</small></div>
                {runtime?.steps?.overridden ? <span className="setting-badge">工作区覆盖</span> : null}
              </div>
              <div className="inline-setting">
                <input
                  aria-label="最大步骤"
                  type="number"
                  min={stepMinimum}
                  max={stepMaximum}
                  value={stepDraft}
                  disabled={busy}
                  onChange={(event) => {
                    setStepDraft(event.target.value);
                    if (stepFeedback.state !== "idle") {
                      setStepFeedback({ state: "idle", message: "" });
                    }
                  }}
                />
                <button
                  type="button"
                  className="primary-small"
                  disabled={busy || pendingStepAction !== null || Number(stepDraft) < stepMinimum || Number(stepDraft) > stepMaximum}
                  onClick={() => {
                    const value = Number(stepDraft);
                    const accepted = props.onStepsChange(value);
                    if (accepted === false) {
                      setStepFeedback({ state: "error", message: "运行时未连接，保存失败" });
                      return;
                    }
                    setPendingStepAction({ kind: "set", value });
                    setStepFeedback({ state: "saving", message: "正在保存…" });
                  }}
                >{pendingStepAction?.kind === "set" ? "保存中…" : "保存"}</button>
                <button
                  type="button"
                  className="text-action"
                  disabled={busy || pendingStepAction !== null}
                  onClick={() => {
                    const accepted = props.onStepsReset();
                    if (accepted === false) {
                      setStepFeedback({ state: "error", message: "运行时未连接，恢复失败" });
                      return;
                    }
                    setPendingStepAction({ kind: "reset" });
                    setStepFeedback({ state: "saving", message: "正在恢复默认值…" });
                  }}
                >{pendingStepAction?.kind === "reset" ? "恢复中…" : "恢复默认"}</button>
              </div>
              {stepFeedback.state !== "idle" ? (
                <div
                  className={`setting-feedback is-${stepFeedback.state}`}
                  role="status"
                  aria-label="最大步骤保存状态"
                >
                  <span aria-hidden="true">{stepFeedback.state === "saved" ? "✓" : stepFeedback.state === "error" ? "!" : "·"}</span>
                  {stepFeedback.message}
                </div>
              ) : null}
            </section>
              </>
            ) : null}

            {tab === "run" ? (
            <section className="settings-card" aria-labelledby="verification-setting-title">
              <div className="settings-card-heading">
                <div>
                  <strong id="verification-setting-title">自动验证</strong>
                  <small>文件变更后按行执行；失败结果会回传 Agent，最多修复两轮</small>
                </div>
                {runtime?.verification?.commands?.length ? (
                  <span className="setting-badge">项目规则</span>
                ) : null}
              </div>
              <textarea
                className="verification-command-input mono-label"
                aria-label="项目验证命令"
                rows={Math.max(3, Math.min(6, verificationDraft.split("\n").length + 1))}
                value={verificationDraft}
                disabled={busy}
                placeholder={"例如：\npython -m pytest -q\npython -m ruff check ."}
                onChange={(event) => {
                  setVerificationDraft(event.target.value);
                  setVerificationFeedback("");
                }}
              />
              <div className="settings-card-footer">
                <small>命令仍受权限审批、危险命令硬阻断与当前 Step 预算约束。</small>
                <button
                  type="button"
                  className="primary-small"
                  disabled={busy}
                  onClick={() => {
                    const commands = verificationDraft
                      .split(/\r?\n/)
                      .map((command) => command.trim())
                      .filter(Boolean);
                    const accepted = props.onVerificationChange(commands);
                    if (accepted === false) {
                      setVerificationFeedback("运行时未连接，保存失败");
                      return;
                    }
                    setVerificationPending(commands.join("\n"));
                    setVerificationFeedback("正在保存…");
                  }}
                >保存验证规则</button>
              </div>
              {verificationFeedback ? (
                <div className="setting-feedback" role="status">{verificationFeedback}</div>
              ) : null}
            </section>
            ) : null}
          </div>
        ) : null}

        {tab === "resources" ? (
          <div className="resource-manager">
            <div className="resource-switcher" role="tablist" aria-label="项目资源">
              <button type="button" className={resourceTab === "files" ? "is-active" : ""} onClick={() => setResourceTab("files")}>文件</button>
              <button type="button" className={resourceTab === "skills" ? "is-active" : ""} onClick={() => setResourceTab("skills")}>Skills</button>
              <button type="button" className={resourceTab === "memory" ? "is-active" : ""} onClick={() => setResourceTab("memory")}>Memory</button>
            </div>
            {resourceTab === "files" ? (
              <div className="resource-panel resource-file-browser">
                {resourcePaths.length ? (
                  <ResourceFileTree
                    paths={resourcePaths}
                    statuses={resourceStatuses}
                    selectedPath={resourcePreviewPath}
                    onSelect={(path) => {
                      setResourcePreviewPath(path);
                      onPreview(path);
                    }}
                  />
                ) : <div className="resource-empty">当前会话还没有读取或修改文件</div>}
                {resourcePreviewPath ? (
                  filePreview && filePreview.path.replaceAll("\\", "/") === resourcePreviewPath
                    ? <FilePreview file={filePreview} />
                    : <div className="resource-preview-loading" role="status">正在读取 {resourcePreviewPath}…</div>
                ) : (
                  resourcePaths.length ? <div className="resource-preview-empty">选择文件以查看只读预览</div> : null
                )}
              </div>
            ) : resourceTab === "skills" ? (
              <div className="resource-panel">
                <div className="resource-toolbar">
                  <input type="search" value={skillQuery} onChange={(event) => setSkillQuery(event.target.value)} placeholder="搜索 Skills" aria-label="搜索 Skills" />
                  <button type="button" className="text-action" disabled={busy} onClick={props.onSkillsReload}>重新加载</button>
                </div>
                <div className="resource-list">
                  {skillItems.map((item) => {
                    const name = valueText(item.name);
                    const enabled = item.enabled !== false;
                    return (
                      <label className="resource-row" key={name}>
                        <span><strong className="mono-label">${name}</strong><small>{valueText(item.description)}</small><i>{valueText(item.source, "user")}</i></span>
                        <input type="checkbox" checked={enabled} disabled={busy} onChange={(event) => props.onSkillToggle(name, event.target.checked)} />
                      </label>
                    );
                  })}
                  {!skillItems.length ? <div className="resource-empty">没有匹配的 Skill</div> : null}
                </div>
              </div>
            ) : (
              <div className="resource-panel">
                <div className="memory-header">
                  <label className="toggle-line"><span><strong>注入长期记忆</strong><small>按项目隔离，不保存秘密</small></span><input type="checkbox" checked={memoryState?.enabled ?? false} disabled={busy} onChange={(event) => props.onMemoryToggle(event.target.checked)} /></label>
                </div>
                <form className="memory-add" onSubmit={(event) => { event.preventDefault(); const value = memoryDraft.trim(); if (!value) return; props.onRemember(value); setMemoryDraft(""); }}>
                  <input value={memoryDraft} disabled={busy} onChange={(event) => setMemoryDraft(event.target.value)} placeholder="添加一条已确认事实" aria-label="新记忆" />
                  <button type="submit" className="primary-small" disabled={busy || !memoryDraft.trim()}>添加</button>
                </form>
                <div className="resource-list">
                  {(memoryState?.items ?? []).map((item) => {
                    const id = valueText(item.id);
                    return (
                      <div className={`memory-row${valueBool(item.enabled) ? "" : " is-disabled"}`} key={id}>
                        <span><strong>{valueText(item.content)}</strong><small>{valueText(item.kind, "fact")} · {id}</small></span>
                        {valueBool(item.enabled) ? <button type="button" className="text-action" disabled={busy} onClick={() => props.onForget(id)}>Forget</button> : null}
                      </div>
                    );
                  })}
                  {!memoryState?.items?.length ? <div className="resource-empty">当前项目还没有长期记忆</div> : null}
                </div>
                <button
                  type="button"
                  className={clearArmed ? "danger-action is-armed" : "danger-action"}
                  disabled={busy || !memoryState?.items?.length}
                  onClick={() => {
                    if (!clearArmed) { setClearArmed(true); return; }
                    props.onMemoryClear();
                    setClearArmed(false);
                  }}
                >{clearArmed ? "再次点击，确认清空" : "清空项目记忆"}</button>
              </div>
            )}
          </div>
        ) : null}

        {tab === "context" ? (
          <div className="inspector-overview inspector-stack">
            <div className="context-ring" style={{ "--usage": `${contextPercent ?? 0}%` } as CSSProperties}>
              <strong>{contextPercent ?? 0}%</strong>
              <span>已使用</span>
            </div>
            <dl className="runtime-facts">
              <div><dt>估算请求</dt><dd>{runtime?.context?.estimated_tokens?.toLocaleString() ?? 0} tokens</dd></div>
              <div><dt>上下文窗口</dt><dd>{runtime?.context?.context_window?.toLocaleString() ?? 0} tokens</dd></div>
            </dl>
            <div className="context-breakdown" aria-label="上下文组成估算">
              {Object.entries(runtime?.context?.breakdown ?? {}).map(([key, value]) => {
                const total = runtime?.context?.estimated_tokens || 1;
                const labels: Record<string, string> = {
                  system_and_project: "系统与项目资源",
                  conversation_and_results: "对话与工具结果",
                  tool_schemas: "工具定义",
                  other: "协议开销",
                };
                return <div key={key}><span>{labels[key] ?? key}</span><b>{value.toLocaleString()} tokens</b><i style={{ width: `${Math.min(100, value * 100 / total)}%` }} /></div>;
              })}
            </div>
            <p className="inspector-note">估算包含系统指令、对话消息和工具定义。Compact 只压缩较早上下文，不删除本地 JSONL 会话记录。</p>
            <button type="button" className="secondary-wide" disabled={busy} onClick={props.onCompact}>Compact 较早上下文</button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
