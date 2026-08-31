import { useMemo, useState } from "react";

import {
  configuredModels,
  inspectBaseUrl,
  providerPresets,
  type ModelCompatibility,
} from "./modelProviders";

export interface ModelSetupInput {
  provider: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  compatibility: ModelCompatibility;
  preserveCredential: boolean;
}

export interface ModelUpdateInput {
  provider: string;
  originalModel: string;
  model: string;
  baseUrl: string;
  compatibility: ModelCompatibility;
}

export interface ManagedModelProvider {
  name?: string;
  base_url?: string | null;
  default_model?: string;
  models?: string[];
  compatibility?: ModelCompatibility;
  managed?: boolean;
  active?: boolean;
}

interface ModelManagerProps {
  busy: boolean;
  providers?: ManagedModelProvider[];
  activeProvider?: string;
  activeModel?: string;
  onConfigure: (input: ModelSetupInput) => Promise<{ persisted: boolean; backend: string }>;
  onUpdateModel?: (input: ModelUpdateInput) => Promise<void> | void;
  onDeleteModel?: (provider: string, model: string) => Promise<void> | void;
}

type EditorMode = "add" | "edit" | "copy";

interface EditorTarget {
  provider: ManagedModelProvider;
  model: string;
}

function modelKey(provider: string, model: string): string {
  return `${provider}\0${model}`;
}

function copyModelName(model: string, providers: ManagedModelProvider[]): string {
  const existing = new Set(providers.flatMap((provider) => configuredModels(provider)));
  let candidate = `${model}-copy`;
  let index = 2;
  while (existing.has(candidate)) candidate = `${model}-copy-${index++}`;
  return candidate;
}

export function ModelManager({
  busy,
  providers = [],
  activeProvider,
  activeModel,
  onConfigure,
  onUpdateModel,
  onDeleteModel,
}: ModelManagerProps) {
  const [preset, setPreset] = useState("openrouter");
  const [provider, setProvider] = useState("openrouter");
  const [baseUrl, setBaseUrl] = useState("https://openrouter.ai/api/v1");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [compatibility, setCompatibility] = useState<ModelCompatibility>("openai");
  const [mode, setMode] = useState<EditorMode | null>(null);
  const [target, setTarget] = useState<EditorTarget | null>(null);
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [deleteArmed, setDeleteArmed] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [collapsedProviders, setCollapsedProviders] = useState<Set<string>>(() => new Set());
  const selectedPreset = providerPresets.find((item) => item.id === preset);
  const inspection = useMemo(() => inspectBaseUrl(baseUrl), [baseUrl]);
  const managedProviders = providers.filter((item) => item.managed !== false);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleProviders = managedProviders.flatMap((item) => {
    const name = item.name ?? "未命名";
    const models = configuredModels(item);
    if (!normalizedQuery) return [{ item, name, models }];
    const providerMatches = name.toLocaleLowerCase().includes(normalizedQuery);
    const matchingModels = providerMatches
      ? models
      : models.filter((modelId) => modelId.toLocaleLowerCase().includes(normalizedQuery));
    return matchingModels.length ? [{ item, name, models: matchingModels }] : [];
  });

  const resetEditor = () => {
    setMode(null);
    setTarget(null);
    setStatus("");
  };

  const startAdd = () => {
    const initial = providerPresets[0];
    setMode("add");
    setTarget(null);
    setPreset(initial.id);
    setProvider(initial.provider);
    setBaseUrl(initial.baseUrl);
    setModel("");
    setApiKey("");
    setCompatibility(initial.compatibility);
    setDeleteArmed(null);
    setStatus("");
  };

  const startModelEditor = (
    item: ManagedModelProvider,
    modelId: string,
    nextMode: "edit" | "copy",
  ) => {
    const name = item.name ?? "";
    setMode(nextMode);
    setTarget({ provider: item, model: modelId });
    setPreset("custom");
    setProvider(name);
    setBaseUrl(item.base_url ?? "");
    setModel(nextMode === "copy" ? copyModelName(modelId, providers) : modelId);
    setCompatibility(item.compatibility ?? "openai");
    setApiKey("");
    setDeleteArmed(null);
    setStatus("");
  };

  if (mode === null) {
    return (
      <div className="model-manager model-manager-list">
        <div className="model-manager-toolbar">
          <div>
            <strong>模型列表</strong>
            <small>管理当前可用模型。</small>
          </div>
          <button type="button" className="primary-small" disabled={busy} onClick={startAdd}>
            添加模型
          </button>
        </div>

        <label className="model-manager-search">
          <span className="sr-only">搜索模型或服务商</span>
          <input
            aria-label="搜索模型或服务商"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索模型或服务商"
          />
        </label>

        {visibleProviders.length ? (
          <div className="model-provider-list" aria-label="已保存的模型">
            {visibleProviders.map(({ item, name, models }) => {
              const allModels = configuredModels(item);
              const collapsed = collapsedProviders.has(name) && !normalizedQuery;
              return (
                <section className="model-provider-entry" key={name}>
                  <button
                    type="button"
                    className="model-provider-heading"
                    aria-expanded={!collapsed}
                    onClick={() => setCollapsedProviders((current) => {
                      const next = new Set(current);
                      if (next.has(name)) next.delete(name);
                      else next.add(name);
                      return next;
                    })}
                  >
                    <span><strong>{name}</strong><small>{allModels.length} 个模型</small></span>
                    <i aria-hidden="true">{collapsed ? "›" : "⌄"}</i>
                  </button>
                  {!collapsed ? (
                    <div className="model-entry-list">
                      {models.map((modelId) => {
                        const key = modelKey(name, modelId);
                        const active = name === activeProvider && modelId === activeModel;
                        return (
                          <div className={`model-entry-row${active ? " is-active" : ""}`} key={key}>
                            <div className="model-entry-identity">
                              <strong className="mono-label">{modelId}</strong>
                              <small>
                                {modelId === item.default_model ? "默认模型" : "可用模型"}
                                {active ? <span>当前</span> : null}
                              </small>
                            </div>
                            <div className="model-entry-actions">
                              <button
                                type="button"
                                aria-label={`编辑 ${name} / ${modelId}`}
                                disabled={busy || !onUpdateModel}
                                onClick={() => startModelEditor(item, modelId, "edit")}
                              >编辑</button>
                              <button
                                type="button"
                                aria-label={`复制 ${name} / ${modelId}`}
                                disabled={busy}
                                onClick={() => startModelEditor(item, modelId, "copy")}
                              >复制</button>
                              {deleteArmed === key ? (
                                <button
                                  type="button"
                                  className="danger-text"
                                  aria-label={`确认删除 ${name} / ${modelId}`}
                                  disabled={busy || active || !onDeleteModel}
                                  onClick={() => {
                                    setSubmitting(true);
                                    Promise.resolve(onDeleteModel?.(name, modelId))
                                      .then(() => setStatus(`已提交 ${modelId} 的删除请求。`))
                                      .catch((error: unknown) => setStatus(
                                        error instanceof Error ? error.message : "删除失败",
                                      ))
                                      .finally(() => {
                                        setDeleteArmed(null);
                                        setSubmitting(false);
                                      });
                                  }}
                                >确认删除</button>
                              ) : (
                                <button
                                  type="button"
                                  aria-label={`删除 ${name} / ${modelId}`}
                                  title={active ? "请先切换到其他模型" : "删除模型"}
                                  disabled={busy || active || !onDeleteModel}
                                  onClick={() => setDeleteArmed(key)}
                                >删除</button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </section>
              );
            })}
          </div>
        ) : (
          <div className="model-manager-empty">
            {managedProviders.length ? "没有匹配的模型。" : "尚未保存模型连接。"}
          </div>
        )}
        {status ? <p className="model-manager-status" role="status">{status}</p> : null}
      </div>
    );
  }

  const siblingCount = target ? configuredModels(target.provider).length : 0;
  const editorTitle = mode === "edit"
    ? `编辑 ${target?.model ?? model}`
    : mode === "copy"
      ? `复制 ${target?.model ?? "模型"}`
      : "添加模型";

  return (
    <div className="model-manager">
      <div className="model-editor-heading">
        <div>
          <h3>{editorTitle}</h3>
          <small>
            {mode === "edit" ? "保存后不会切换当前模型。" : "保存一个可在上方直接切换的模型。"}
          </small>
        </div>
        <button type="button" className="text-action" disabled={submitting} onClick={resetEditor}>
          取消
        </button>
      </div>
      <form
        className="model-editor-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (inspection.error) return;
          setSubmitting(true);
          setStatus("");
          const operation = mode === "edit" && target && onUpdateModel
            ? Promise.resolve(onUpdateModel({
                provider,
                originalModel: target.model,
                model,
                baseUrl: inspection.normalized,
                compatibility,
              }))
            : onConfigure({
                provider,
                baseUrl: inspection.normalized,
                model,
                apiKey,
                compatibility,
                preserveCredential: mode === "copy",
              });
          void operation
            .then(() => {
              setApiKey("");
              setMode(null);
              setTarget(null);
              setStatus(mode === "edit" ? "模型修改已保存。" : "模型已保存，正在重新加载连接…");
            })
            .catch((error: unknown) => {
              setStatus(error instanceof Error ? error.message : "模型配置失败");
            })
            .finally(() => setSubmitting(false));
        }}
      >
        {mode === "add" ? (
          <>
            <label>
              <span>服务商模板</span>
              <select
                aria-label="服务商模板"
                value={preset}
                disabled={busy || submitting}
                onChange={(event) => {
                  const next = event.target.value;
                  const value = providerPresets.find((item) => item.id === next);
                  if (!value) return;
                  setPreset(next);
                  setProvider(value.provider);
                  setBaseUrl(value.baseUrl);
                  setCompatibility(value.compatibility);
                  setStatus(value.note);
                }}
              >
                {providerPresets.map((item) => (
                  <option value={item.id} key={item.id}>{item.label}</option>
                ))}
              </select>
            </label>
            {selectedPreset?.note ? <p className="model-preset-note">{selectedPreset.note}</p> : null}
          </>
        ) : null}
        <label>
          <span>服务商名称</span>
          <input
            aria-label="服务商名称"
            value={provider}
            required
            pattern="[A-Za-z0-9_.-]+"
            disabled={busy || submitting || mode !== "add"}
            onChange={(event) => setProvider(event.target.value)}
          />
        </label>
        {mode !== "add" && siblingCount > 1 ? (
          <p className="model-shared-connection-note">
            连接设置由 {provider} 下的 {siblingCount} 个模型共享。
          </p>
        ) : null}
        <label>
          <span>Base URL</span>
          <input
            aria-label="Base URL"
            type="url"
            value={baseUrl}
            required
            disabled={busy || submitting}
            onChange={(event) => setBaseUrl(event.target.value)}
            placeholder="https://provider.example/v1"
          />
        </label>
        {inspection.error ? (
          <div className="model-url-preview is-error" role="status">
            <small>{inspection.error}</small>
            {inspection.suggestion ? (
              <button type="button" onClick={() => setBaseUrl(inspection.suggestion ?? "")}>
                改用建议地址
              </button>
            ) : null}
          </div>
        ) : (
          <p className="model-url-helper" role="status">
            请求地址 <code>{inspection.requestUrl}</code>
          </p>
        )}
        <label>
          <span>Model ID</span>
          <input
            aria-label="Model ID"
            className="mono-label"
            value={model}
            required
            disabled={busy || submitting}
            onChange={(event) => setModel(event.target.value)}
            placeholder="例如 deepseek-chat"
          />
        </label>
        {mode === "add" ? (
          <>
            <label>
              <span>API Key</span>
              <input
                aria-label="API Key"
                type="password"
                autoComplete="new-password"
                value={apiKey}
                disabled={busy || submitting}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="留空则使用当前环境变量"
              />
            </label>
            <p className="model-secret-note">
              API Key 仅通过桌面安全凭据通道写入系统密钥库，不会进入会话或配置文件。
            </p>
          </>
        ) : null}
        <button type="submit" className="primary-wide" disabled={busy || submitting || Boolean(inspection.error)}>
          {submitting ? "正在保存…" : mode === "edit" ? "保存修改" : "保存模型"}
        </button>
      </form>
      {status ? <p className="model-manager-status" role="status">{status}</p> : null}
    </div>
  );
}
