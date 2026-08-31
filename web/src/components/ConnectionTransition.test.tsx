import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ConnectionTransition } from "./ConnectionTransition";

test("presents one animated startup state and reveals slow-start help", () => {
  vi.useFakeTimers();
  const view = render(
    <ConnectionTransition state="connecting" ready={false} error="" />,
  );

  expect(screen.getByRole("status", { name: "正在启动本地 Agent" })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  expect(screen.queryByText("启动可能需要更长时间")).not.toBeInTheDocument();

  act(() => vi.advanceTimersByTime(8_000));
  expect(screen.getByText("启动可能需要更长时间")).toBeInTheDocument();

  view.rerender(<ConnectionTransition state="connected" ready error="" />);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  vi.useRealTimers();
});

test("explains an expected model-runtime restart without presenting it as a failure", () => {
  render(
    <ConnectionTransition
      state="connecting"
      ready={false}
      error=""
      activity="model-restart"
    />,
  );

  expect(screen.getByRole("status", { name: "正在应用模型配置" })).toHaveTextContent(
    "重启本地 Agent 并恢复当前会话",
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("keeps project switching in a purposeful transition state", () => {
  render(
    <ConnectionTransition
      state="connecting"
      ready={false}
      error=""
      activity="workspace-restart"
    />,
  );

  expect(screen.getByRole("status", { name: "正在切换项目" })).toHaveTextContent(
    "恢复该项目最近使用的会话",
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("turns connection failure into recoverable primary actions", async () => {
  const user = userEvent.setup();
  const onRetry = vi.fn();
  const onOpenSettings = vi.fn();
  render(
    <ConnectionTransition
      state="error"
      ready={false}
      error="连接被拒绝"
      onRetry={onRetry}
      onOpenSettings={onOpenSettings}
    />,
  );

  expect(screen.getByRole("alert", { name: "无法连接本地 Agent" })).toHaveTextContent(
    "连接被拒绝",
  );
  await user.click(screen.getByRole("button", { name: "重新连接" }));
  await user.click(screen.getByRole("button", { name: "检查模型设置" }));
  expect(onRetry).toHaveBeenCalledOnce();
  expect(onOpenSettings).toHaveBeenCalledOnce();
});
