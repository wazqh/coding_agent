import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ModelManager } from "./ModelManager";

test("collects one provider setup without exposing the API key as plain text", async () => {
  const user = userEvent.setup();
  const onConfigure = vi.fn(async () => ({ persisted: true, backend: "dpapi" }));
  render(<ModelManager busy={false} onConfigure={onConfigure} />);

  expect(screen.queryByLabelText("服务商模板")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "添加连接" }));
  await user.selectOptions(screen.getByLabelText("服务商模板"), "custom");
  await user.type(screen.getByLabelText("服务商名称"), "my-provider");
  await user.type(screen.getByLabelText("Base URL"), "https://models.example/v1");
  await user.type(screen.getByLabelText("Model ID"), "fast-model");
  await user.type(screen.getByLabelText("API Key"), "top-secret");

  expect(screen.getByLabelText("API Key")).toHaveAttribute("type", "password");
  await user.click(screen.getByRole("button", { name: "保存并切换" }));

  expect(onConfigure).toHaveBeenCalledWith({
    provider: "my-provider",
    baseUrl: "https://models.example/v1",
    model: "fast-model",
    apiKey: "top-secret",
    compatibility: "openai",
    preserveCredential: false,
  });
  expect(await screen.findByText("配置已保存，正在重启并验证模型连接…"))
    .toBeInTheDocument();
  expect(screen.queryByLabelText("服务商模板")).not.toBeInTheDocument();
});

test("allows an existing provider environment variable to supply the API key", async () => {
  const user = userEvent.setup();
  const onConfigure = vi.fn(async () => ({ persisted: true, backend: "dpapi" }));
  render(<ModelManager busy={false} onConfigure={onConfigure} />);

  await user.click(screen.getByRole("button", { name: "添加连接" }));
  await user.selectOptions(screen.getByLabelText("服务商模板"), "gemini");
  await user.type(screen.getByLabelText("Model ID"), "gemini-2.5-flash");
  await user.click(screen.getByRole("button", { name: "保存并切换" }));

  expect(onConfigure).toHaveBeenCalledWith({
    provider: "gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.5-flash",
    apiKey: "",
    compatibility: "gemini",
    preserveCredential: false,
  });
});

test("explains and corrects a full chat completions endpoint before saving", async () => {
  const user = userEvent.setup();
  const onConfigure = vi.fn(async () => ({ persisted: true, backend: "dpapi" }));
  render(<ModelManager busy={false} onConfigure={onConfigure} />);

  await user.click(screen.getByRole("button", { name: "添加连接" }));
  await user.selectOptions(screen.getByLabelText("服务商模板"), "custom");
  await user.type(screen.getByLabelText("服务商名称"), "zhipu");
  await user.type(
    screen.getByLabelText("Base URL"),
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  );
  await user.type(screen.getByLabelText("Model ID"), "glm-4.5");

  expect(screen.getByText("这里应填写 API 根地址；Forge 会自动追加 /chat/completions。"))
    .toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存并切换" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "改用建议地址" }));

  expect(screen.getByLabelText("Base URL")).toHaveValue("https://open.bigmodel.cn/api/paas/v4");
  expect(screen.getByText("https://open.bigmodel.cn/api/paas/v4/chat/completions"))
    .toBeInTheDocument();
});

test("renders one manageable row per switchable model and edits the selected model", async () => {
  const user = userEvent.setup();
  const onConfigure = vi.fn(async () => ({ persisted: true, backend: "dpapi" }));
  const onUpdateModel = vi.fn(async () => undefined);
  const onDeleteModel = vi.fn(async () => undefined);
  render(
    <ModelManager
      busy={false}
      onConfigure={onConfigure}
      onUpdateModel={onUpdateModel}
      onDeleteModel={onDeleteModel}
      activeProvider="GLM"
      activeModel="glm-5.3-flash"
      providers={[{
        name: "GLM",
        base_url: "https://open.bigmodel.cn/api/paas/v4",
        default_model: "glm-5.3-flash",
        models: ["glm-5.3-flash", "glm-5.2-flash"],
        compatibility: "openai",
        managed: true,
      }]}
    />,
  );

  expect(screen.getByRole("button", { name: "编辑 GLM / glm-5.3-flash" }))
    .toBeInTheDocument();
  expect(screen.getByRole("button", { name: "编辑 GLM / glm-5.2-flash" }))
    .toBeInTheDocument();
  expect(screen.getByText("当前")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "编辑 GLM / glm-5.2-flash" }));
  expect(screen.getByRole("heading", { name: "编辑 glm-5.2-flash" })).toBeInTheDocument();
  expect(screen.getByText("连接设置由 GLM 下的 2 个模型共享。")).toBeInTheDocument();
  await user.clear(screen.getByLabelText("Model ID"));
  await user.type(screen.getByLabelText("Model ID"), "glm-5.2-air");
  await user.click(screen.getByRole("button", { name: "保存修改" }));

  expect(onUpdateModel).toHaveBeenCalledWith({
    provider: "GLM",
    originalModel: "glm-5.2-flash",
    model: "glm-5.2-air",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    compatibility: "openai",
  });
});

test("filters large model catalogs by model id or provider", async () => {
  const user = userEvent.setup();
  render(
    <ModelManager
      busy={false}
      onConfigure={vi.fn(async () => ({ persisted: true, backend: "dpapi" }))}
      onUpdateModel={vi.fn(async () => undefined)}
      onDeleteModel={vi.fn(async () => undefined)}
      providers={[
        {
          name: "GLM",
          default_model: "glm-5.3-flash",
          models: ["glm-5.2-flash", "glm-5.3-flash"],
          managed: true,
        },
        {
          name: "deepseek",
          default_model: "deepseek-chat",
          models: ["deepseek-chat"],
          managed: true,
        },
      ]}
    />,
  );

  expect(screen.getByText("glm-5.2-flash")).toBeInTheDocument();
  await user.type(screen.getByLabelText("搜索模型或服务商"), "deep");

  expect(screen.getByText("deepseek-chat")).toBeInTheDocument();
  expect(screen.queryByText("glm-5.2-flash")).not.toBeInTheDocument();
});
