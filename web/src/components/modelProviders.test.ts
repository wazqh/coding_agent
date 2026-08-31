import { describe, expect, test } from "vitest";

import {
  configuredModels,
  inspectBaseUrl,
  modelOptions,
  providerPresets,
} from "./modelProviders";

describe("provider presets", () => {
  test("covers direct providers and regional MaaS gateways", () => {
    const ids = providerPresets.map((preset) => preset.id);

    expect(ids).toEqual(expect.arrayContaining([
      "openai",
      "kimi-cn",
      "kimi-global",
      "deepseek",
      "qwen-cn",
      "zhipu",
      "hunyuan",
      "tencent-maas-cn",
      "alibaba-maas",
      "huawei-maas",
      "gemini",
      "custom",
    ]));
  });
});

describe("inspectBaseUrl", () => {
  test("previews the final chat completions request", () => {
    expect(inspectBaseUrl("https://api.openai.com/v1/")).toEqual({
      normalized: "https://api.openai.com/v1",
      requestUrl: "https://api.openai.com/v1/chat/completions",
    });
  });

  test("detects a copied resource endpoint and offers the API root", () => {
    expect(inspectBaseUrl("https://open.bigmodel.cn/api/paas/v4/chat/completions")).toEqual({
      normalized: "https://open.bigmodel.cn/api/paas/v4/chat/completions",
      requestUrl: "https://open.bigmodel.cn/api/paas/v4/chat/completions/chat/completions",
      suggestion: "https://open.bigmodel.cn/api/paas/v4",
      error: "这里应填写 API 根地址；Forge 会自动追加 /chat/completions。",
    });
  });

  test("rejects non-http URLs and embedded credentials", () => {
    expect(inspectBaseUrl("file:///tmp/model").error).toContain("HTTP");
    expect(inspectBaseUrl("https://user:secret@example.com/v1").error).toContain("凭据");
  });
});

describe("model catalog presentation", () => {
  test("uses one de-duplicated model list for switching and provider summaries", () => {
    const provider = {
      name: "GLM",
      default_model: "glm-5.3-flash",
      models: ["glm-5.2-flash", "glm-5.3-flash", "glm-5.2-flash"],
    };

    expect(configuredModels(provider)).toEqual(["glm-5.3-flash", "glm-5.2-flash"]);
    expect(modelOptions([provider])).toEqual([
      {
        provider: "GLM",
        model: "glm-5.3-flash",
        value: "GLM\0glm-5.3-flash",
        label: "glm-5.3-flash · GLM",
      },
      {
        provider: "GLM",
        model: "glm-5.2-flash",
        value: "GLM\0glm-5.2-flash",
        label: "glm-5.2-flash · GLM",
      },
    ]);
  });

  test("keeps the same model id from different providers selectable", () => {
    expect(modelOptions([
      { name: "direct", default_model: "shared" },
      { name: "router", default_model: "shared" },
    ]).map((option) => option.value)).toEqual([
      "direct\0shared",
      "router\0shared",
    ]);
  });
});
