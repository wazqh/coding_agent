import { useState } from "react";

export interface ModelSetupInput {
  provider: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  compatibility: "openai" | "gemini";
}

interface ModelManagerProps {
  busy: boolean;
  onConfigure: (input: ModelSetupInput) => Promise<{ persisted: boolean; backend: string }>;
}

const presets = {
  openrouter: { provider: "openrouter", baseUrl: "https://openrouter.ai/api/v1", compatibility: "openai" as const },
  deepseek: { provider: "deepseek", baseUrl: "https://api.deepseek.com/v1", compatibility: "openai" as const },
  gemini: { provider: "gemini", baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai", compatibility: "gemini" as const },
  custom: { provider: "", baseUrl: "", compatibility: "openai" as const },
};

export function ModelManager({ busy, onConfigure }: ModelManagerProps) {
  const [preset, setPreset] = useState<keyof typeof presets>("openrouter");
  const [provider, setProvider] = useState(presets.openrouter.provider);
  const [baseUrl, setBaseUrl] = useState(presets.openrouter.baseUrl);
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [compatibility, setCompatibility] = useState<"openai" | "gemini">("openai");
  const [status, setStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);

  return (
    <form
      className="model-manager"
      onSubmit={(event) => {
        event.preventDefault();
        setSubmitting(true);
        setStatus("");
        void onConfigure({ provider, baseUrl, model, apiKey, compatibility })
          .then((result) => {
            setApiKey("");
            setStatus(
              result.persisted
                ? "配置已保存，正在重启本地运行时…"
                : "系统密钥存储不可用；本次仅在内存中使用，正在重启…",
            );
          })
          .catch((error: unknown) => {
            setStatus(error instanceof Error ? error.message : "模型配置失败");
          })
          .finally(() => setSubmitting(false));
      }}
    >
      <label>
        <span>服务商模板</span>
        <select
          aria-label="服务商模板"
          value={preset}
          disabled={busy || submitting}
          onChange={(event) => {
            const next = event.target.value as keyof typeof presets;
            const value = presets[next];
            setPreset(next);
            setProvider(value.provider);
            setBaseUrl(value.baseUrl);
            setCompatibility(value.compatibility);
          }}
        >
          <option value="openrouter">OpenRouter</option>
          <option value="deepseek">DeepSeek</option>
          <option value="gemini">Gemini</option>
          <option value="custom">自定义 OpenAI-compatible</option>
        </select>
      </label>
      <label>
        <span>服务商名称</span>
        <input aria-label="服务商名称" value={provider} required pattern="[A-Za-z0-9_.-]+" disabled={busy || submitting} onChange={(event) => setProvider(event.target.value)} />
      </label>
      <label>
        <span>Base URL</span>
        <input aria-label="Base URL" type="url" value={baseUrl} required disabled={busy || submitting} onChange={(event) => setBaseUrl(event.target.value)} />
      </label>
      <label>
        <span>Model ID</span>
        <input aria-label="Model ID" className="mono-label" value={model} required disabled={busy || submitting} onChange={(event) => setModel(event.target.value)} placeholder="例如 anthropic/claude-sonnet-4" />
      </label>
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
        可直接粘贴密钥或环境变量赋值；API Key 不会发送到 WebSocket、Python 会话或 models.toml。
      </p>
      <button type="submit" className="primary-wide" disabled={busy || submitting}>
        {submitting ? "正在保存…" : "保存并切换"}
      </button>
      {status ? <p className="model-manager-status" role="status">{status}</p> : null}
    </form>
  );
}
