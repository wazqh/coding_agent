import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ModelManager } from "./ModelManager";

test("collects one provider setup without exposing the API key as plain text", async () => {
  const user = userEvent.setup();
  const onConfigure = vi.fn(async () => ({ persisted: true, backend: "dpapi" }));
  render(<ModelManager busy={false} onConfigure={onConfigure} />);

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
  });
  expect(await screen.findByText("配置已保存，正在重启本地运行时…")).toBeInTheDocument();
});

test("allows an existing provider environment variable to supply the API key", async () => {
  const user = userEvent.setup();
  const onConfigure = vi.fn(async () => ({ persisted: true, backend: "dpapi" }));
  render(<ModelManager busy={false} onConfigure={onConfigure} />);

  await user.selectOptions(screen.getByLabelText("服务商模板"), "gemini");
  await user.type(screen.getByLabelText("Model ID"), "gemini-2.5-flash");
  await user.click(screen.getByRole("button", { name: "保存并切换" }));

  expect(onConfigure).toHaveBeenCalledWith({
    provider: "gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.5-flash",
    apiKey: "",
    compatibility: "gemini",
  });
});
