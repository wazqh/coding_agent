import { useEffect, useMemo, useState, type CSSProperties } from "react";

import type {
  ChangeSummary,
  FilePreviewData,
  MemoryState,
  ModelCatalogState,
  RuntimeState,
  SkillsState,
  TimelineItem,
  VerificationCheckState,
  VerificationModeState,
  VerificationProcedureState,
} from "../state/store";
import { ChangesSummary } from "./ChangesSummary";
import { ChangeReviewPane } from "./ChangeReviewPane";
import { ActivityDetailPane } from "./ActivityDetailPane";
import { ChevronIcon, CloseIcon } from "./icons";
import { ModelManager, type ModelSetupInput, type ModelUpdateInput } from "./ModelManager";
import { modelOptions } from "./modelProviders";
import { ResourceFileTree, type ResourceFileStatus } from "./ResourceFileTree";
import { ResourcePreviewPane } from "./ResourcePreviewPane";
import { SkillCreator } from "./SkillCreator";

export type InspectorTab = "changes" | "run" | "settings" | "resources" | "context";

function checksFromRuntime(runtime: RuntimeState | null): VerificationCheckState[] {
  if (runtime?.verification?.checks?.length) {
    return runtime.verification.checks.map((check) => ({
      ...check,
      target_paths: check.target_paths ?? [],
    }));
  }
  return (runtime?.verification?.commands ?? []).map((command, index) => ({
    id: `legacy-${index + 1}`,
    label: `验证 ${index + 1}`,
    kind: "custom",
    command,
    cwd: ".",
    timeout_seconds: 120,
    enabled: true,
  }));
}

interface ContextDrawerProps {
  width: number;
  onWidthChange: (width: number) => void;
  onClose: () => void;
  changes: ChangeSummary[];
  filePreview: FilePreviewData | null;
  onPreview: (path: string) => void;
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
  initialRunPanel?: "commands" | "verification";
  openModelManager?: boolean;
  onTabChange?: (tab: InspectorTab) => void;
  onRuntimeRefresh: () => void;
  onModelList: () => void;
  onModelSelect: (provider: string, modelId: string) => void;
  onModelReload: () => void;
  onModelProviderConfigure: (
    input: ModelSetupInput,
  ) => Promise<{ persisted: boolean; backend: string }>;
  onModelProviderDelete: (provider: string) => void;
  onModelUpdate: (input: ModelUpdateInput) => Promise<void> | void;
  onModelDelete: (provider: string, model: string) => Promise<void> | void;
  onPermissionChange: (mode: "prompt" | "auto" | "read-only") => void;
  onStepsChange: (value: number) => boolean | void;
  onStepsReset: () => boolean | void;
  onVerificationChange: (config: {
    mode: VerificationModeState;
    checks: VerificationCheckState[];
    procedures: VerificationProcedureState[];
  }) => boolean | void;
  onMemoryList: () => void;
  onMemoryToggle: (enabled: boolean) => void;
  onRemember: (content: string) => void;
  onForget: (id: string) => void;
  onMemoryClear: () => void;
  onSkillsList: () => void;
  onSkillToggle: (name: string, enabled: boolean) => void;
  onSkillsReload: () => void;
  onSkillDraft: (
    requirement: string,
    template: "custom" | "review" | "testing" | "documentation",
  ) => boolean | void;
  onSkillCreate: (input: {
    scope: "user" | "repo";
    name: string;
    description: string;
    instructions: string;
  }) => boolean | void;
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
  const [tab, setTab] = useState<InspectorTab>(initialTab);
  const [runPanel, setRunPanel] = useState<"commands" | "verification">(
    props.initialRunPanel ?? "commands",
  );
  const [resourceTab, setResourceTab] = useState<"files" | "skills" | "memory">("files");
  const [resourcePreviewPath, setResourcePreviewPath] = useState<string | null>(null);
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(null);
  const [skillQuery, setSkillQuery] = useState("");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [clearArmed, setClearArmed] = useState(false);
  const [stepDraft, setStepDraft] = useState(String(runtime?.steps?.current ?? 40));
  const [pendingStepAction, setPendingStepAction] = useState<
    { kind: "set"; value: number } | { kind: "reset" } | null
  >(null);
  const [stepFeedback, setStepFeedback] = useState<
    { state: "idle" | "saving" | "saved" | "error"; message: string }
  >({ state: "idle", message: "" });
  const [verificationChecks, setVerificationChecks] = useState<VerificationCheckState[]>(
    checksFromRuntime(runtime),
  );
  const [verificationMode, setVerificationMode] = useState<VerificationModeState>(
    runtime?.verification?.mode
      ?? (runtime?.verification?.agent_tdd ? "agent_tdd" : runtime?.verification?.enabled ? "checks" : "off"),
  );
  const [verificationProcedures, setVerificationProcedures] = useState<VerificationProcedureState[]>(
    runtime?.verification?.procedures ?? [],
  );
  const [verificationPending, setVerificationPending] = useState<string | null>(null);
  const [verificationFeedback, setVerificationFeedback] = useState("");
  const [verificationRulePickerOpen, setVerificationRulePickerOpen] = useState(false);
  const verificationSuggestions = runtime?.verification?.suggestions ?? [];
  const workspaceVerificationTemplates = runtime?.verification?.workspace_templates ?? [];
  const [modelManagerOpen, setModelManagerOpen] = useState(props.openModelManager ?? false);
  const pendingChanges = useMemo(
    () => changes.filter((change) => change.reviewStatus !== "accepted"),
    [changes],
  );
  const selected = pendingChanges.find((change) => change.id === selectedId);
  const commandItems = props.timelineItems.filter(
    (item): item is Extract<TimelineItem, { kind: "activity" }> =>
      item.kind === "activity" && item.activityKind === "command",
  );
  const validationItems = props.timelineItems.filter(
    (item): item is Extract<TimelineItem, { kind: "activity" }> =>
      item.kind === "activity" && item.activityKind === "validation",
  );
  const selectedActivity = [...commandItems, ...validationItems]
    .find((item) => item.id === selectedActivityId);
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
    setSelectedActivityId(null);
  }, [tab, runPanel]);

  useEffect(() => {
    setStepDraft(String(runtime?.steps?.current ?? 40));
  }, [runtime?.steps?.current]);

  useEffect(() => {
    const checks = checksFromRuntime(runtime);
    const mode = runtime?.verification?.mode
      ?? (runtime?.verification?.agent_tdd ? "agent_tdd" : runtime?.verification?.enabled ? "checks" : "off");
    const procedures = runtime?.verification?.procedures ?? [];
    const current = JSON.stringify({ mode, checks, procedures });
    setVerificationChecks(checks);
    setVerificationMode(mode);
    setVerificationProcedures(procedures);
    if (verificationPending !== null && verificationPending === current) {
      setVerificationPending(null);
      setVerificationFeedback(mode === "off" ? "自动验证已关闭" : "验证设置已保存到当前会话");
    }
  }, [
    runtime?.verification?.mode,
    runtime?.verification?.enabled,
    runtime?.verification?.agent_tdd,
    runtime?.verification?.checks,
    runtime?.verification?.procedures,
    runtime?.verification?.commands,
  ]);

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
      ? runtime?.steps?.current === pendingStepAction.value && runtime?.steps?.overridden === true
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
    if (selectedId === null || pendingChanges.some((change) => change.id === selectedId)) return;
    const previousIndex = changes.findIndex((change) => change.id === selectedId);
    const next = previousIndex >= 0
      ? [...changes.slice(previousIndex + 1), ...changes.slice(0, previousIndex)]
        .find((change) => change.reviewStatus !== "accepted")
      : pendingChanges[0];
    setSelectedId(next?.id ?? null);
  }, [changes, pendingChanges, selectedId]);

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
  const availableModels = modelOptions(modelCatalog?.providers ?? []);
  const stepMinimum = runtime?.steps?.minimum ?? 30;
  const stepMaximum = runtime?.steps?.maximum ?? 999;
  const verificationProcedureEditor = (
    <>
      <div className="verification-procedure-heading">
        <span>
          <h3>检验规程</h3>
          <small>用自然语言告诉 Agent 何时新增、重跑或收紧验证规则。</small>
        </span>
        <button
          type="button"
          className="secondary-small"
          disabled={busy || verificationProcedures.length >= 12}
          onClick={() => setVerificationProcedures((current) => [...current, {
            id: `procedure-${Date.now().toString(36)}-${current.length + 1}`,
            instruction: "",
            enabled: true,
          }])}
        >添加规程</button>
      </div>
      <div className="verification-procedure-list">
        {verificationProcedures.map((procedure, index) => (
          <label className="verification-procedure" key={procedure.id}>
            <input
              type="checkbox"
              aria-label={`启用检验规程 ${index + 1}`}
              checked={procedure.enabled}
              disabled={busy}
              onChange={(event) => setVerificationProcedures((current) => current.map(
                (item, itemIndex) => itemIndex === index
                  ? { ...item, enabled: event.target.checked }
                  : item,
              ))}
            />
            <textarea
              aria-label={`检验规程 ${index + 1}`}
              value={procedure.instruction}
              disabled={busy}
              placeholder="例如：依赖文件变化后，必须重跑原有测试和构建规则。"
              onChange={(event) => setVerificationProcedures((current) => current.map(
                (item, itemIndex) => itemIndex === index
                  ? { ...item, instruction: event.target.value }
                  : item,
              ))}
            />
            <button
              type="button"
              aria-label={`删除检验规程 ${index + 1}`}
              disabled={busy}
              onClick={() => setVerificationProcedures((current) => current.filter(
                (_, itemIndex) => itemIndex !== index,
              ))}
            >删除</button>
          </label>
        ))}
      </div>
    </>
  );

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
            {value === "changes" && pendingChanges.length ? ` ${pendingChanges.length}` : ""}
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
              }}
              onReviewAll={props.onReviewAll}
              busy={busy}
            />
          </>
        ) : null}

        {tab === "run" || tab === "settings" ? (
          <div className="inspector-overview inspector-stack">
            {tab === "run" ? (
              <>
                <div className="run-section-tabs" role="tablist" aria-label="运行面板">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={runPanel === "commands"}
                    className={runPanel === "commands" ? "is-active" : ""}
                    onClick={() => setRunPanel("commands")}
                  >命令记录</button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={runPanel === "verification"}
                    className={runPanel === "verification" ? "is-active" : ""}
                    onClick={() => setRunPanel("verification")}
                  >验证</button>
                </div>

                {runPanel === "commands" ? (
                  <>
                    <section className="settings-card inspector-run-history" aria-label="命令记录">
                      <div className="settings-card-heading">
                        <div><strong>命令记录</strong><small>Agent 实际执行的命令、退出状态与结果</small></div>
                      </div>
                      {commandItems.length ? commandItems.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className={`run-history-row is-${item.status}`}
                          aria-label={`查看命令详情：${item.summary}`}
                          onClick={() => setSelectedActivityId(item.id)}
                        >
                          <span>命令</span>
                          <strong>{item.summary}</strong>
                          <i>{item.status === "completed" ? "完成" : item.status === "failed" ? "失败" : "执行中"}</i>
                          <ChevronIcon />
                        </button>
                      )) : <div className="resource-empty">当前会话还没有命令记录</div>}
                    </section>
                    <div className="inspector-status-card">
                      <span className={busy ? "status-pulse" : "health-dot"} />
                      <div>
                        <strong>{busy ? "正在执行任务" : "运行时已就绪"}</strong>
                        <small>{busy ? "运行期间设置保持只读" : "命令仍受审批、工作区边界和硬安全规则保护"}</small>
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <section className="settings-card verification-settings" aria-labelledby="verification-setting-title">
                      <div className="settings-card-heading">
                        <div>
                          <strong id="verification-setting-title">验证方式</strong>
                          <small>仅用于当前会话；验证命令统一由本地验证层执行</small>
                        </div>
                      </div>
                      <div className="verification-mode-picker" role="radiogroup" aria-label="验证方式">
                        {([
                          ["off", "关闭", "不自动执行，文件变更后仍可手动验证"],
                          ["checks", "规则验证", "文件变更后执行匹配的已配置规则"],
                          ["agent_tdd", "Agent TDD", "Agent 编写独立测试并登记规则，验证层统一执行"],
                        ] as const).map(([mode, label, description]) => (
                          <button
                            key={mode}
                            type="button"
                            role="radio"
                            aria-checked={verificationMode === mode}
                            className={verificationMode === mode ? "is-selected" : ""}
                            disabled={busy}
                            onClick={() => {
                              setVerificationMode(mode);
                              setVerificationRulePickerOpen(false);
                              setVerificationFeedback("");
                            }}
                          >
                            <strong>{label}</strong>
                            <small>{description}</small>
                          </button>
                        ))}
                      </div>
                      {verificationMode === "off" ? (
                        <div className="verification-mode-note" role="note">
                          <strong>自动验证已关闭</strong>
                          <span>关闭后不会在回合结束时自动执行命令。</span>
                        </div>
                      ) : null}
                      {verificationMode === "agent_tdd" ? (
                        <div className="verification-tdd-flow">
                          <div className="verification-mode-note is-tdd" role="note">
                            <strong>先定义规程，再登记规则</strong>
                            <span>先告诉 Agent 何时需要新增、重跑或收紧测试，再由它登记可执行规则。</span>
                          </div>
                          {verificationProcedureEditor}
                        </div>
                      ) : null}
                      {verificationMode !== "off" ? (
                        <>
                      <div className="verification-rule-heading">
                        <span>
                          <h3>{verificationMode === "agent_tdd" ? "Agent 验证规则" : "验证规则"}</h3>
                          <small>每条规则拥有独立的工作目录、命令和超时。</small>
                        </span>
                        <button
                          type="button"
                          className="secondary-small"
                          disabled={busy || verificationChecks.length >= 8}
                          onClick={() => {
                            setVerificationRulePickerOpen((current) => !current);
                            setVerificationFeedback("");
                          }}
                        >{verificationRulePickerOpen ? "收起" : "添加规则"}</button>
                      </div>
                      {!verificationChecks.length ? (
                        <div className="verification-empty-note" role="note">
                          先选择下方检测到的命令，或添加项目实际使用的测试、构建规则。
                        </div>
                      ) : null}
                      {verificationRulePickerOpen ? (
                        <div className="verification-rule-picker">
                          <button
                            type="button"
                            className="verification-blank-rule"
                            disabled={busy || verificationChecks.length >= 8}
                            onClick={() => {
                              const number = verificationChecks.length + 1;
                              setVerificationChecks((current) => [...current, {
                                id: `check-${Date.now().toString(36)}-${number}`,
                                label: `验证 ${number}`,
                                kind: "custom",
                                command: "",
                                cwd: ".",
                                timeout_seconds: 120,
                                enabled: true,
                              }]);
                              setVerificationRulePickerOpen(false);
                              setVerificationFeedback("已添加空白规则，请填写命令和工作目录");
                            }}
                          >添加空白规则</button>
                      {verificationSuggestions.length ? (
                        <div className="verification-suggestions" role="group" aria-label="检测到的验证命令">
                          <span>项目建议</span>
                          <div>
                            {verificationSuggestions.map((suggestion) => {
                              const selected = verificationChecks.some((check) => (
                                check.command === suggestion.command && check.cwd === suggestion.cwd
                              ));
                              return (
                                <button
                                  key={suggestion.id}
                                  type="button"
                                  className={selected ? "is-selected" : ""}
                                  aria-label={`${selected ? "已添加" : "添加建议命令"} ${suggestion.command}`}
                                  disabled={busy || selected}
                                  onClick={() => {
                                    const number = verificationChecks.length + 1;
                                    setVerificationChecks((current) => [...current, {
                                      id: `suggested-${Date.now().toString(36)}-${number}`,
                                      label: suggestion.label,
                                      kind: suggestion.kind,
                                      command: suggestion.command,
                                      cwd: suggestion.cwd,
                                      timeout_seconds: suggestion.timeout_seconds,
                                      enabled: true,
                                      target_paths: suggestion.target_paths,
                                    }]);
                                    setVerificationRulePickerOpen(false);
                                    setVerificationFeedback(`已添加：${suggestion.label}`);
                                  }}
                                >
                                  <span>{selected ? "✓" : "+"}</span>
                                  <span className="verification-suggestion-copy">
                                    <b>{suggestion.label}</b>
                                    <code>{suggestion.cwd} · {suggestion.command}</code>
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ) : (
                        <div className="verification-guidance" role="note">
                          <strong>没有检测到现成命令</strong>
                          <span>可查看 README 或项目脚本；常见写法包括 pytest、npm test、cargo test。</span>
                        </div>
                      )}
                      {workspaceVerificationTemplates.length ? (
                        <div className="verification-suggestions is-workspace-template" role="group" aria-label="工作区验证模板">
                          <span>工作区模板 <small>导入后仅保存到当前会话</small></span>
                          <div>
                            {workspaceVerificationTemplates.map((template) => {
                              const selected = verificationChecks.some((check) => (
                                check.command === template.command && check.cwd === template.cwd
                              ));
                              return (
                                <button
                                  key={`workspace-${template.id}`}
                                  type="button"
                                  className={selected ? "is-selected" : ""}
                                  disabled={busy || selected}
                                  onClick={() => {
                                    setVerificationChecks((current) => [
                                      ...current,
                                      { ...template, id: `imported-${Date.now().toString(36)}-${current.length + 1}` },
                                    ]);
                                    setVerificationRulePickerOpen(false);
                                    setVerificationFeedback(`已导入到当前会话：${template.label}`);
                                  }}
                                >
                                  <span>{selected ? "✓" : "+"}</span>
                                  <span className="verification-suggestion-copy">
                                    <b>{template.label}</b>
                                    <code>{template.cwd} · {template.command}</code>
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ) : null}
                        </div>
                      ) : null}
                      <div className="verification-rule-list">
                        {verificationChecks.map((check, index) => (
                          <section className="verification-rule" key={check.id}>
                            <div className="verification-rule-card-heading">
                              <span className="verification-rule-identity">
                                <b>规则 {index + 1}</b>
                                {check.source === "agent" ? <em>Agent 登记</em> : null}
                              </span>
                              <button
                                type="button"
                                className="verification-rule-remove"
                                aria-label={`删除验证规则 ${index + 1}`}
                                disabled={busy}
                                onClick={() => setVerificationChecks((current) => current.filter(
                                  (_, itemIndex) => itemIndex !== index,
                                ))}
                              >删除</button>
                            </div>
                            {check.target_paths?.length ? (
                              <small className="verification-rule-coverage">
                                覆盖 {check.target_paths.join("、")}
                              </small>
                            ) : null}
                            <div className="verification-rule-topline">
                              <label>
                                <span>名称</span>
                                <input
                                  aria-label={`验证名称 ${index + 1}`}
                                  value={check.label}
                                  disabled={busy}
                                  onChange={(event) => setVerificationChecks((current) => current.map(
                                    (item, itemIndex) => itemIndex === index
                                      ? { ...item, label: event.target.value }
                                      : item,
                                  ))}
                                />
                              </label>
                              <label>
                                <span>类型</span>
                                <select
                                  aria-label={`验证类型 ${index + 1}`}
                                  value={check.kind}
                                  disabled={busy}
                                  onChange={(event) => setVerificationChecks((current) => current.map(
                                    (item, itemIndex) => itemIndex === index
                                      ? { ...item, kind: event.target.value as VerificationCheckState["kind"] }
                                      : item,
                                  ))}
                                >
                                  <option value="test">测试</option>
                                  <option value="build">构建</option>
                                  <option value="lint">静态检查</option>
                                  <option value="typecheck">类型检查</option>
                                  <option value="custom">自定义</option>
                                </select>
                              </label>
                            </div>
                            <label>
                              <span>命令</span>
                              <input
                                className="mono-label"
                                aria-label={`验证命令 ${index + 1}`}
                                value={check.command}
                                disabled={busy}
                                placeholder="python -m pytest tests -q"
                                onChange={(event) => setVerificationChecks((current) => current.map(
                                  (item, itemIndex) => itemIndex === index
                                    ? { ...item, command: event.target.value }
                                    : item,
                                ))}
                              />
                            </label>
                            <div className="verification-rule-fields">
                              <label>
                                <span>工作目录</span>
                                <input
                                  className="mono-label"
                                  aria-label={`工作目录 ${index + 1}`}
                                  value={check.cwd}
                                  disabled={busy}
                                  placeholder=". 或 algorithm_practice"
                                  onChange={(event) => setVerificationChecks((current) => current.map(
                                    (item, itemIndex) => itemIndex === index
                                      ? { ...item, cwd: event.target.value }
                                      : item,
                                  ))}
                                />
                              </label>
                              <label>
                                <span>超时（秒）</span>
                                <input
                                  type="number"
                                  min={1}
                                  max={3600}
                                  aria-label={`超时秒数 ${index + 1}`}
                                  value={check.timeout_seconds}
                                  disabled={busy}
                                  onChange={(event) => setVerificationChecks((current) => current.map(
                                    (item, itemIndex) => itemIndex === index
                                      ? { ...item, timeout_seconds: Number(event.target.value) }
                                      : item,
                                  ))}
                                />
                              </label>
                            </div>
                            <label>
                              <span>触发路径</span>
                              <input
                                className="mono-label"
                                aria-label={`触发路径 ${index + 1}`}
                                value={(check.target_paths ?? []).join(", ")}
                                disabled={busy}
                                placeholder="例如 src, tests；留空表示任意文件变更"
                                onChange={(event) => setVerificationChecks((current) => current.map(
                                  (item, itemIndex) => itemIndex === index
                                    ? {
                                        ...item,
                                        target_paths: event.target.value
                                          .split(",")
                                          .map((value) => value.trim())
                                          .filter(Boolean),
                                      }
                                    : item,
                                ))}
                              />
                              <small>仅本轮改动命中这些工作区相对路径时执行。</small>
                            </label>
                          </section>
                        ))}
                      </div>
                        </>
                      ) : null}
                      <div className="settings-card-footer">
                        <small>
                          保存即授权当前会话运行完全相同的命令与目录；变更后重新审批，硬安全规则始终生效。
                        </small>
                        <button
                          type="button"
                          className="primary-small"
                          disabled={busy || verificationPending !== null}
                          onClick={() => {
                            const normalizedChecks = verificationChecks.map((check) => ({
                              ...check,
                              label: check.label.trim(),
                              command: check.command.trim(),
                              cwd: check.cwd.trim() || ".",
                              target_paths: [...new Set((check.target_paths ?? []).map((path) => path.trim()).filter(Boolean))],
                            }));
                            const checks = verificationMode === "off"
                              ? normalizedChecks.filter((check) => check.label && check.command)
                              : normalizedChecks;
                            const invalidCwd = checks.some((check) => (
                              /^(?:[A-Za-z]:|[\\/])/.test(check.cwd)
                              || check.cwd.split(/[\\/]+/).includes("..")
                            ));
                            const invalidTarget = checks.some((check) => check.target_paths.some((path) => (
                              /^(?:[A-Za-z]:|[\\/])/.test(path)
                              || path.split(/[\\/]+/).includes("..")
                            )));
                            if (checks.some((check) => !check.label || !check.command)) {
                              setVerificationFeedback("请补全每条验证规则的名称和命令");
                              return;
                            }
                            if (invalidCwd) {
                              setVerificationFeedback("工作目录必须是工作区内的相对路径");
                              return;
                            }
                            if (invalidTarget) {
                              setVerificationFeedback("触发路径必须是工作区内的相对路径");
                              return;
                            }
                            if (verificationMode === "checks" && !checks.some((check) => check.enabled)) {
                              setVerificationFeedback("规则验证至少需要一条已启用的验证规则");
                              return;
                            }
                            const normalizedProcedures = verificationProcedures.map((procedure) => ({
                              ...procedure,
                              instruction: procedure.instruction.trim(),
                            }));
                            const procedures = verificationMode === "agent_tdd"
                              ? normalizedProcedures
                              : normalizedProcedures.filter((procedure) => procedure.instruction);
                            if (verificationMode === "agent_tdd"
                              && procedures.some((procedure) => !procedure.instruction)) {
                              setVerificationFeedback("请补全检验规程内容，或删除空白规程");
                              return;
                            }
                            const accepted = props.onVerificationChange({
                              mode: verificationMode,
                              checks,
                              procedures,
                            });
                            if (accepted === false) {
                              setVerificationFeedback("运行时未连接，保存失败");
                              return;
                            }
                            setVerificationPending(JSON.stringify({
                              mode: verificationMode,
                              checks,
                              procedures,
                            }));
                            setVerificationFeedback("正在保存…");
                          }}
                        >{verificationPending ? "保存中…" : "保存验证设置"}</button>
                      </div>
                      {verificationFeedback ? <div className="setting-feedback" role="status">{verificationFeedback}</div> : null}
                    </section>
                    <section className="settings-card inspector-run-history" aria-label="验证记录">
                      <div className="settings-card-heading">
                        <div><strong>验证记录</strong><small>确定性命令的最近执行证据</small></div>
                      </div>
                      {validationItems.length ? validationItems.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className={`run-history-row is-${item.status}`}
                          aria-label={`查看验证详情：${item.summary}`}
                          onClick={() => setSelectedActivityId(item.id)}
                        >
                          <span>验证</span>
                          <strong>{item.summary}</strong>
                          <i>{item.status === "completed" ? "通过" : item.status === "failed" ? "失败" : "执行中"}</i>
                          <ChevronIcon />
                        </button>
                      )) : <div className="resource-empty">当前会话还没有验证记录</div>}
                    </section>
                  </>
                )}
              </>
            ) : null}

            {tab === "settings" ? (
              <>
            <section className="settings-card" aria-labelledby="model-setting-title">
              <div className="settings-card-heading">
                <div><strong id="model-setting-title">模型</strong><small>OpenAI-compatible 服务商与模型</small></div>
                <div className="settings-card-actions">
                  <button type="button" className="text-action" disabled={busy} onClick={props.onModelReload}>重新加载</button>
                  <button type="button" className={modelManagerOpen ? "primary-small" : "text-action"} disabled={busy} onClick={() => setModelManagerOpen((value) => !value)}>
                    {modelManagerOpen ? "完成" : "管理连接"}
                  </button>
                </div>
              </div>
              {modelManagerOpen ? (
                <ModelManager
                  busy={busy}
                  providers={modelCatalog?.providers}
                  activeProvider={modelCatalog?.active?.provider}
                  activeModel={modelCatalog?.active?.id}
                  onConfigure={props.onModelProviderConfigure}
                  onUpdateModel={props.onModelUpdate}
                  onDeleteModel={props.onModelDelete}
                />
              ) : (
                <select
                  aria-label="当前模型"
                  className="settings-select mono-label"
                  value={modelValue}
                  disabled={busy || !availableModels.length}
                  onChange={(event) => {
                    const [provider, modelId] = event.target.value.split("\0");
                    props.onModelSelect(provider, modelId);
                  }}
                >
                  {!availableModels.length ? <option value={modelValue}>{modelName}</option> : null}
                  {availableModels.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              )}
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
                {resourcePaths.length ? <div className="resource-preview-empty">选择文件，在检查器左侧查看只读预览</div> : null}
              </div>
            ) : resourceTab === "skills" ? (
              <div className="resource-panel">
                <div className="resource-toolbar">
                  <input type="search" value={skillQuery} onChange={(event) => setSkillQuery(event.target.value)} placeholder="搜索 Skills" aria-label="搜索 Skills" />
                  <button type="button" className="text-action" disabled={busy} onClick={props.onSkillsReload}>重新加载</button>
                </div>
                <SkillCreator
                  busy={busy}
                  draft={skillsState?.draft ?? null}
                  items={skillsState?.items ?? []}
                  onDraft={props.onSkillDraft}
                  onCreate={props.onSkillCreate}
                />
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
      {tab === "resources" && resourceTab === "files" && resourcePreviewPath ? (
        <ResourcePreviewPane
          path={resourcePreviewPath}
          drawerWidth={props.width}
          file={filePreview}
          onClose={() => setResourcePreviewPath(null)}
        />
      ) : null}
      {tab === "changes" && selected ? (
        <ChangeReviewPane
          change={selected}
          drawerWidth={props.width}
          busy={busy}
          onReview={props.onReviewChange}
          onClose={() => {
            setSelectedId(null);
          }}
        />
      ) : null}
      {tab === "run" && selectedActivity ? (
        <ActivityDetailPane
          item={selectedActivity}
          drawerWidth={props.width}
          onClose={() => setSelectedActivityId(null)}
        />
      ) : null}
    </aside>
  );
}
