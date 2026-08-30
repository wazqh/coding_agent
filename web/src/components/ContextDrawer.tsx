import { useEffect, useMemo, useState, type CSSProperties } from "react";

import type {
  ChangeSummary,
  FilePreviewData,
  MemoryState,
  ModelCatalogState,
  RuntimeState,
  SkillsState,
} from "../state/store";
import { ChangesSummary } from "./ChangesSummary";
import { DiffViewer } from "./DiffViewer";
import { FilePreview } from "./FilePreview";
import { CloseIcon } from "./icons";
import { ModelManager, type ModelSetupInput } from "./ModelManager";

export type InspectorTab = "changes" | "run" | "resources" | "context";

interface ContextDrawerProps {
  onClose: () => void;
  changes: ChangeSummary[];
  filePreview: FilePreviewData | null;
  onPreview: (path: string) => void;
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
  onStepsChange: (value: number) => void;
  onStepsReset: () => void;
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
  const [tab, setTab] = useState<InspectorTab>(initialTab);
  const [resourceTab, setResourceTab] = useState<"skills" | "memory">("skills");
  const [skillQuery, setSkillQuery] = useState("");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [clearArmed, setClearArmed] = useState(false);
  const [stepDraft, setStepDraft] = useState(String(runtime?.steps?.current ?? 24));
  const [modelManagerOpen, setModelManagerOpen] = useState(props.openModelManager ?? false);
  const selected = changes.find((change) => change.id === selectedId) ?? changes[0];

  useEffect(() => {
    if (props.openModelManager) setModelManagerOpen(true);
  }, [props.openModelManager]);

  useEffect(() => {
    if (tab === "run") {
      props.onRuntimeRefresh();
      props.onModelList();
    } else if (tab === "resources") {
      props.onSkillsList();
      props.onMemoryList();
    }
  }, [tab]);

  useEffect(() => {
    setStepDraft(String(runtime?.steps?.current ?? 24));
  }, [runtime?.steps?.current]);

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
              onSelect={(change) => setSelectedId(change.id)}
            />
            {selected ? <DiffViewer change={selected} onPreview={onPreview} /> : null}
            {filePreview && filePreview.path === selected?.path ? <FilePreview file={filePreview} /> : null}
          </>
        ) : null}

        {tab === "run" ? (
          <div className="inspector-overview inspector-stack">
            <div className="inspector-status-card">
              <span className={busy ? "status-pulse" : "health-dot"} />
              <div>
                <strong>{busy ? "正在执行任务" : "运行时已就绪"}</strong>
                <small>{busy ? "运行期间设置保持只读" : "所有设置仅作用于当前工作区或进程"}</small>
              </div>
            </div>

            <section className="settings-card" aria-labelledby="model-setting-title">
              <div className="settings-card-heading">
                <div><strong id="model-setting-title">模型</strong><small>OpenAI-compatible 服务商与模型</small></div>
                <div className="settings-card-actions">
                  <button type="button" className="text-action" disabled={busy} onClick={props.onModelReload}>重新加载</button>
                  <button type="button" className="primary-small" disabled={busy} onClick={() => setModelManagerOpen((value) => !value)}>
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
                  onChange={(event) => setStepDraft(event.target.value)}
                />
                <button
                  type="button"
                  className="primary-small"
                  disabled={busy || Number(stepDraft) < stepMinimum || Number(stepDraft) > stepMaximum}
                  onClick={() => props.onStepsChange(Number(stepDraft))}
                >保存</button>
                <button type="button" className="text-action" disabled={busy} onClick={props.onStepsReset}>恢复默认</button>
              </div>
            </section>
          </div>
        ) : null}

        {tab === "resources" ? (
          <div className="resource-manager">
            <div className="resource-switcher" role="tablist" aria-label="项目资源">
              <button type="button" className={resourceTab === "skills" ? "is-active" : ""} onClick={() => setResourceTab("skills")}>Skills</button>
              <button type="button" className={resourceTab === "memory" ? "is-active" : ""} onClick={() => setResourceTab("memory")}>Memory</button>
            </div>
            {resourceTab === "skills" ? (
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
            <p className="inspector-note">估算包含系统指令、对话消息和工具定义。Compact 只压缩较早上下文，不删除本地 JSONL 会话记录。</p>
            <button type="button" className="primary-wide" disabled={busy} onClick={props.onCompact}>Compact 较早上下文</button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
