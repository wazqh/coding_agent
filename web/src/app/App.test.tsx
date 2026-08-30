import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";

const baseProps = {
  productName: "Forge Test Brand",
  workspaceName: "coding_agent",
  workspacePath: "D:\\codes\\coding_agent",
  modelName: "gemini-3.7-flash",
  permissions: "prompt" as const,
};

test("renders the Chinese agent workbench with injected branding", () => {
  render(<App {...baseProps} />);

  expect(screen.getByText("Forge Test Brand")).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "项目与对话" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "新对话" })).toBeInTheDocument();
  expect(screen.getByRole("main", { name: "Agent 会话" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "任务输入" })).toBeInTheDocument();
  expect(screen.getByText("gemini-3.7-flash")).toBeInTheDocument();
  expect(screen.getByText("询问")).toBeInTheDocument();
  expect(screen.queryByRole("complementary", { name: "任务检查器" })).not.toBeInTheDocument();
});

test("opens and closes the task inspector", async () => {
  const user = userEvent.setup();
  render(<App {...baseProps} />);

  await user.click(screen.getByRole("button", { name: "任务检查器" }));
  expect(screen.getByRole("complementary", { name: "任务检查器" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "变更" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "关闭检查器" }));
  expect(screen.queryByRole("complementary", { name: "任务检查器" })).not.toBeInTheDocument();
});

test("busy state keeps stop available and locks session-changing actions", () => {
  render(<App {...baseProps} busy />);

  expect(screen.getByRole("button", { name: "停止任务" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "新对话" })).toBeDisabled();
  expect(screen.getByText("正在执行")).toBeInTheDocument();
});

