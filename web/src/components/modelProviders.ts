export type ModelCompatibility = "openai" | "gemini";

export interface ProviderPreset {
  id: string;
  label: string;
  provider: string;
  baseUrl: string;
  compatibility: ModelCompatibility;
  note: string;
}

export const providerPresets: ProviderPreset[] = [
  { id: "openrouter", label: "OpenRouter", provider: "openrouter", baseUrl: "https://openrouter.ai/api/v1", compatibility: "openai", note: "聚合多个模型服务商" },
  { id: "openai", label: "OpenAI", provider: "openai", baseUrl: "https://api.openai.com/v1", compatibility: "openai", note: "OpenAI 官方 API" },
  { id: "kimi-cn", label: "Kimi（中国）", provider: "kimi", baseUrl: "https://api.moonshot.cn/v1", compatibility: "openai", note: "Moonshot 中国站" },
  { id: "kimi-global", label: "Kimi（全球）", provider: "kimi-global", baseUrl: "https://api.moonshot.ai/v1", compatibility: "openai", note: "Moonshot 国际站" },
  { id: "deepseek", label: "DeepSeek", provider: "deepseek", baseUrl: "https://api.deepseek.com", compatibility: "openai", note: "DeepSeek 官方 API" },
  { id: "qwen-cn", label: "通义千问 / DashScope", provider: "qwen", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", compatibility: "openai", note: "阿里云百炼中国站" },
  { id: "zhipu", label: "智谱 GLM", provider: "zhipu", baseUrl: "https://open.bigmodel.cn/api/paas/v4", compatibility: "openai", note: "智谱通用开放平台" },
  { id: "zhipu-coding", label: "智谱 Coding Plan", provider: "zhipu-coding", baseUrl: "https://open.bigmodel.cn/api/coding/paas/v4", compatibility: "openai", note: "仅适用于 Coding Plan" },
  { id: "hunyuan", label: "腾讯混元", provider: "hunyuan", baseUrl: "https://api.hunyuan.cloud.tencent.com/v1", compatibility: "openai", note: "混元 OpenAI-compatible 接口" },
  { id: "tencent-maas-cn", label: "腾讯云 MaaS（中国）", provider: "tencent-maas", baseUrl: "https://tokenhub.tencentmaas.com/v1", compatibility: "openai", note: "TokenHub 中国站" },
  { id: "tencent-maas-global", label: "腾讯云 MaaS（国际）", provider: "tencent-maas-global", baseUrl: "https://tokenhub-intl.tencentmaas.com/v1", compatibility: "openai", note: "TokenHub 国际站" },
  { id: "alibaba-maas", label: "阿里云百炼 MaaS", provider: "alibaba-maas", baseUrl: "", compatibility: "openai", note: "请粘贴与 API Key 同地域的工作空间根地址" },
  { id: "huawei-maas", label: "华为云 ModelArts MaaS", provider: "huawei-maas", baseUrl: "", compatibility: "openai", note: "请粘贴控制台提供的区域根地址，例如 …modelarts-maas.com/openai/v1" },
  { id: "gemini", label: "Google Gemini", provider: "gemini", baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai", compatibility: "gemini", note: "Gemini OpenAI compatibility" },
  { id: "custom", label: "自定义 OpenAI-compatible", provider: "", baseUrl: "", compatibility: "openai", note: "适用于自托管或其他兼容服务" },
];

export interface BaseUrlInspection {
  normalized: string;
  requestUrl?: string;
  suggestion?: string;
  error?: string;
}

export interface CatalogProvider {
  name?: string;
  default_model?: string;
  models?: string[];
}

export interface ModelOption {
  provider: string;
  model: string;
  value: string;
  label: string;
}

export function configuredModels(provider: CatalogProvider): string[] {
  const models = [provider.default_model, ...(provider.models ?? [])]
    .map((model) => model?.trim())
    .filter((model): model is string => Boolean(model));
  return [...new Set(models)];
}

export function modelOptions(providers: CatalogProvider[]): ModelOption[] {
  return providers.flatMap((provider) => {
    const name = provider.name?.trim();
    if (!name) return [];
    return configuredModels(provider).map((model) => ({
      provider: name,
      model,
      value: `${name}\0${model}`,
      label: `${model} · ${name}`,
    }));
  });
}

const resourceEndpoint = /\/(?:chat\/completions|completions|responses|models)$/i;

export function inspectBaseUrl(value: string): BaseUrlInspection {
  const normalized = value.trim().replace(/\/+$/, "");
  if (!normalized) return { normalized, error: "请输入服务商提供的 API 根地址。" };
  let parsed: URL;
  try {
    parsed = new URL(normalized);
  } catch {
    return { normalized, error: "Base URL 必须是有效的 HTTP 或 HTTPS 地址。" };
  }
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.host) {
    return { normalized, error: "Base URL 必须是有效的 HTTP 或 HTTPS 地址。" };
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    return { normalized, error: "Base URL 不能包含凭据、查询参数或片段。" };
  }
  const requestUrl = `${normalized}/chat/completions`;
  const match = resourceEndpoint.exec(parsed.pathname.replace(/\/+$/, ""));
  if (match) {
    const rootPath = parsed.pathname.slice(0, match.index).replace(/\/+$/, "");
    parsed.pathname = rootPath || "/";
    parsed.search = "";
    parsed.hash = "";
    return {
      normalized,
      requestUrl,
      suggestion: parsed.toString().replace(/\/+$/, ""),
      error: "这里应填写 API 根地址；Forge 会自动追加 /chat/completions。",
    };
  }
  return { normalized, requestUrl };
}
