import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { Composer } from "./Composer";

test("sends with Enter and keeps Shift+Enter for a newline", async () => {
  const user = userEvent.setup();
  const onSend = vi.fn();
  render(
    <Composer
      busy={false}
      modelName="gemini-flash"
      permissions="prompt"
      onSend={onSend}
      onStop={() => undefined}
    />,
  );

  const input = screen.getByRole("textbox", { name: "任务输入" });
  await user.type(input, "第一行{shift>}{enter}{/shift}第二行");
  expect(onSend).not.toHaveBeenCalled();
  await user.keyboard("{Enter}");

  expect(onSend).toHaveBeenCalledWith("第一行\n第二行");
  expect(input).toHaveValue("");
});

test("keeps stop available while a turn is running", async () => {
  const user = userEvent.setup();
  const onStop = vi.fn();
  render(
    <Composer
      busy
      modelName="gemini-flash"
      permissions="prompt"
      onSend={() => undefined}
      onStop={onStop}
    />,
  );

  expect(screen.getByRole("textbox", { name: "任务输入" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "停止任务" }));
  expect(onStop).toHaveBeenCalledOnce();
});

test("does not accept or clear a task before the transport is ready", async () => {
  const user = userEvent.setup();
  const onSend = vi.fn();
  render(
    <Composer
      busy={false}
      ready={false}
      modelName="gemini-flash"
      permissions="prompt"
      onSend={onSend}
    />,
  );

  const input = screen.getByRole("textbox", { name: "任务输入" });
  expect(input).toBeDisabled();
  expect(screen.getByText("正在连接")).toBeInTheDocument();
  expect(onSend).not.toHaveBeenCalled();
});

test("shows live context usage without hiding the runtime controls", () => {
  render(
    <Composer
      busy={false}
      modelName="gemini-flash"
      permissions="prompt"
      contextPercent={40}
    />,
  );

  expect(screen.getByText("上下文 40%")).toBeInTheDocument();
  expect(screen.getByText("gemini-flash")).toBeInTheDocument();
});

test("keeps keyboard-selected completions visible and applies them with Tab", async () => {
  const user = userEvent.setup();
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  const onSend = vi.fn();
  const completion = {
    text: "/",
    cursor: 1,
    items: [
      {
        kind: "command" as const,
        label: "/help",
        insert_text: "/help",
        description: "查看帮助",
        replace_start: 0,
        replace_end: 1,
      },
      {
        kind: "command" as const,
        label: "/status",
        insert_text: "/status",
        description: "查看状态",
        replace_start: 0,
        replace_end: 1,
      },
    ],
  };
  render(
    <Composer
      busy={false}
      modelName="gemini-flash"
      permissions="prompt"
      completion={completion}
      onSend={onSend}
    />,
  );

  const input = screen.getByRole("textbox", { name: "任务输入" });
  await user.type(input, "/");
  await user.keyboard("{ArrowDown}");

  expect(screen.getByRole("option", { name: /status/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });

  await user.keyboard("{Tab}");
  expect(input).toHaveValue("/status");
  expect(onSend).not.toHaveBeenCalled();
  expect(input).toHaveFocus();
});
