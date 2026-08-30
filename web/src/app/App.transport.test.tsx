import { StrictMode } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import type { ConnectionState, Transport, ViewEvent } from "../protocol/types";
import { createAgentStore } from "../state/store";
import { App } from "./App";

class FakeTransport implements Transport {
  connect = vi.fn(async () => undefined);
  request = vi.fn(() => true);
  close = vi.fn();
  private listener: ((event: ViewEvent) => void) | null = null;
  private statusListener: ((status: ConnectionState) => void) | null = null;

  subscribe(listener: (event: ViewEvent) => void) {
    this.listener = listener;
    return () => {
      this.listener = null;
    };
  }

  subscribeStatus(listener: (status: ConnectionState) => void) {
    this.statusListener = listener;
    return () => {
      this.statusListener = null;
    };
  }

  emit(event: ViewEvent) {
    this.listener?.(event);
  }

  emitStatus(status: ConnectionState) {
    this.statusListener?.(status);
  }
}

const baseProps = {
  productName: "Forge Test Brand",
  workspaceName: "当前项目",
  workspacePath: "正在连接本地运行时…",
  modelName: "未连接",
  permissions: "prompt" as const,
};

test("connects transport, renders semantic events, and sends a turn", async () => {
  const user = userEvent.setup();
  const transport = new FakeTransport();
  const store = createAgentStore();
  render(<App {...baseProps} transport={transport} store={store} />);

  expect(screen.getByRole("textbox", { name: "任务输入" })).toBeDisabled();
  await waitFor(() => expect(transport.connect).toHaveBeenCalledOnce());
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "snapshot",
      seq: 1,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        workspace_name: "coding_agent",
        workspace_path: "D:\\codes\\coding_agent",
        model: "gemini-flash",
        permissions: "prompt",
        busy: false,
      },
    });
    transport.emit({
      protocol_version: 2,
      type: "turn.started",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: "turn-1",
      data: { task: "检查项目" },
    });
    transport.emit({
      protocol_version: 2,
      type: "message.final",
      seq: 3,
      session_id: "a".repeat(24),
      turn_id: "turn-1",
      data: { role: "assistant", content: "检查完成。" },
    });
  });

  expect(within(screen.getByRole("main", { name: "Agent 会话" })).getByText("检查项目"))
    .toBeInTheDocument();
  expect(screen.getByText("检查完成。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "gemini-flash" })).toBeInTheDocument();

  act(() => store.setState({ busy: false }));
  const input = screen.getByRole("textbox", { name: "任务输入" });
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "运行测试{Enter}");
  expect(transport.request).toHaveBeenCalledWith("turn.start", { task: "运行测试" });
});

test("StrictMode setup does not close the shared transport", async () => {
  const transport = new FakeTransport();
  render(
    <StrictMode>
      <App {...baseProps} transport={transport} store={createAgentStore()} />
    </StrictMode>,
  );

  await waitFor(() => expect(transport.connect).toHaveBeenCalled());
  expect(transport.close).not.toHaveBeenCalled();
});

test("keeps task input gated until the runtime snapshot arrives", async () => {
  const transport = new FakeTransport();
  render(<App {...baseProps} transport={transport} store={createAgentStore()} />);
  await waitFor(() => expect(transport.connect).toHaveBeenCalledOnce());

  act(() => transport.emitStatus("connected"));

  expect(screen.getByRole("textbox", { name: "任务输入" })).toBeDisabled();
});

test("disables input after disconnect and offers reconnection", async () => {
  const user = userEvent.setup();
  const transport = new FakeTransport();
  render(<App {...baseProps} transport={transport} store={createAgentStore()} />);
  await waitFor(() => expect(transport.connect).toHaveBeenCalledOnce());
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "snapshot",
      seq: 1,
      session_id: "a".repeat(24),
      turn_id: null,
      data: { busy: false },
    });
    transport.emitStatus("disconnected");
  });

  expect(screen.getByRole("textbox", { name: "任务输入" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "重新连接" }));
  expect(transport.connect).toHaveBeenCalledTimes(2);
});

test("creates or resumes sessions and requests changes for the contextual drawer", async () => {
  const user = userEvent.setup();
  const transport = new FakeTransport();
  const store = createAgentStore();
  render(<App {...baseProps} transport={transport} store={store} />);
  await waitFor(() => expect(transport.connect).toHaveBeenCalledOnce());

  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "snapshot",
      seq: 1,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        workspace_name: "coding_agent",
        workspace_path: "D:\\codes\\coding_agent",
        model: "gemini-flash",
        permissions: "prompt",
        busy: false,
        sessions: [
          {
            id: "b".repeat(24),
            title: "修复测试",
            updated_at: "2026-08-29T10:00:00Z",
            model: "gemini-flash",
          },
        ],
      },
    });
  });

  await user.click(screen.getByRole("button", { name: "新对话" }));
  await user.click(screen.getByRole("treeitem", { name: /修复测试/ }));
  await user.click(screen.getByRole("button", { name: "任务检查器" }));

  expect(transport.request).toHaveBeenCalledWith("session.create");
  expect(transport.request).toHaveBeenCalledWith("session.resume", {
    session_id: "b".repeat(24),
  });
  expect(transport.request).toHaveBeenCalledWith("changes.list");

  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "changes.updated",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        changes: [
          {
            id: "change-1",
            path: "src/demo.py",
            additions: 1,
            deletions: 0,
            diff: "--- a/src/demo.py\n+++ b/src/demo.py\n@@ -0,0 +1 @@\n+hello\n",
          },
        ],
      },
    });
  });

  expect(await screen.findByRole("button", { name: /src\/demo.py/ })).toBeInTheDocument();
  expect(screen.getByText("hello")).toBeInTheDocument();
});

test("configures a provider through desktop IPC without sending the API key over transport", async () => {
  const user = userEvent.setup();
  const transport = new FakeTransport();
  const saveProviderCredential = vi.fn(async () => ({
    persisted: true,
    backend: "dpapi",
    transactionId: "transaction-1",
  }));
  const commitProviderCredential = vi.fn(async () => true);
  const rollbackProviderCredential = vi.fn(async () => true);
  const restartGateway = vi.fn(async () => undefined);
  Object.defineProperty(window, "forgeDesktop", {
    configurable: true,
    value: {
      runtimeInfo: vi.fn(),
      selectWorkspace: vi.fn(),
      saveProviderCredential,
      commitProviderCredential,
      rollbackProviderCredential,
      restartGateway,
      openExternal: vi.fn(),
      minimize: vi.fn(),
      toggleMaximize: vi.fn(),
      close: vi.fn(),
    },
  });
  render(<App {...baseProps} transport={transport} store={createAgentStore()} desktop />);
  await waitFor(() => expect(transport.connect).toHaveBeenCalledOnce());
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "snapshot",
      seq: 1,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        workspace_name: "coding_agent",
        workspace_path: "D:\\codes\\coding_agent",
        model: "gemini-flash",
        permissions: "prompt",
        busy: false,
      },
    });
  });

  await user.type(screen.getByRole("textbox", { name: "任务输入" }), "/model{Enter}");
  await user.type(await screen.findByLabelText("Model ID"), "vendor/fast-model");
  await user.type(screen.getByLabelText("API Key"), "top-secret");
  await user.click(screen.getByRole("button", { name: "保存并切换" }));

  await waitFor(() => expect(saveProviderCredential).toHaveBeenCalledWith({
    provider: "openrouter",
    apiKey: "top-secret",
  }));
  expect(transport.request).toHaveBeenCalledWith("model.provider.upsert", {
    provider: "openrouter",
    base_url: "https://openrouter.ai/api/v1",
    model: "vendor/fast-model",
    compatibility: "openai",
  });
  expect(JSON.stringify(transport.request.mock.calls)).not.toContain("top-secret");

  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "command.completed",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: null,
      data: { command: "model.provider.upsert", status: "completed" },
    });
  });
  await waitFor(() => expect(commitProviderCredential).toHaveBeenCalledWith("transaction-1"));
  await waitFor(() => expect(restartGateway).toHaveBeenCalledWith({
    workspace: "D:\\codes\\coding_agent",
    sessionId: "a".repeat(24),
  }));
  Reflect.deleteProperty(window, "forgeDesktop");
});

test("rolls back a staged provider credential when metadata persistence fails", async () => {
  const user = userEvent.setup();
  const transport = new FakeTransport();
  const rollbackProviderCredential = vi.fn(async () => true);
  const restartGateway = vi.fn(async () => undefined);
  Object.defineProperty(window, "forgeDesktop", {
    configurable: true,
    value: {
      runtimeInfo: vi.fn(),
      selectWorkspace: vi.fn(),
      saveProviderCredential: vi.fn(async () => ({
        persisted: true,
        backend: "dpapi",
        transactionId: "transaction-1",
      })),
      commitProviderCredential: vi.fn(async () => true),
      rollbackProviderCredential,
      restartGateway,
      openExternal: vi.fn(),
      minimize: vi.fn(),
      toggleMaximize: vi.fn(),
      close: vi.fn(),
    },
  });
  render(<App {...baseProps} transport={transport} store={createAgentStore()} desktop />);
  await waitFor(() => expect(transport.connect).toHaveBeenCalledOnce());
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "snapshot",
      seq: 1,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        workspace_name: "coding_agent",
        workspace_path: "D:\\codes\\coding_agent",
        model: "gemini-flash",
        permissions: "prompt",
        busy: false,
      },
    });
  });

  await user.type(screen.getByRole("textbox", { name: "任务输入" }), "/model{Enter}");
  await user.type(await screen.findByLabelText("Model ID"), "vendor/fast-model");
  await user.type(screen.getByLabelText("API Key"), "top-secret");
  await user.click(screen.getByRole("button", { name: "保存并切换" }));
  await waitFor(() => expect(transport.request).toHaveBeenCalledWith(
    "model.provider.upsert",
    expect.any(Object),
  ));

  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "error",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: null,
      data: { message: "cannot update model catalog" },
    });
  });

  await waitFor(() => expect(rollbackProviderCredential).toHaveBeenCalledWith("transaction-1"));
  expect(restartGateway).not.toHaveBeenCalled();
  Reflect.deleteProperty(window, "forgeDesktop");
});

test("shows project picker progress and restarts the desktop gateway for the selected folder", async () => {
  const user = userEvent.setup();
  const transport = new FakeTransport();
  let resolveSelection: (value: string | null) => void = () => undefined;
  const selection = new Promise<string | null>((resolve) => {
    resolveSelection = resolve;
  });
  const selectWorkspace = vi.fn(() => selection);
  const restartGateway = vi.fn(async () => undefined);
  Object.defineProperty(window, "forgeDesktop", {
    configurable: true,
    value: {
      runtimeInfo: vi.fn(),
      selectWorkspace,
      saveProviderCredential: vi.fn(),
      restartGateway,
      openExternal: vi.fn(),
      minimize: vi.fn(),
      toggleMaximize: vi.fn(),
      close: vi.fn(),
    },
  });

  render(<App {...baseProps} transport={transport} store={createAgentStore()} desktop />);
  await waitFor(() => expect(transport.connect).toHaveBeenCalledOnce());
  await user.click(screen.getByRole("button", { name: "添加项目" }));

  expect(screen.getByRole("button", { name: "正在添加项目" })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  expect(screen.getByRole("status")).toHaveTextContent("正在打开目录选择器…");

  resolveSelection("D:\\codes\\selected-project");
  await waitFor(() =>
    expect(restartGateway).toHaveBeenCalledWith({ workspace: "D:\\codes\\selected-project" }),
  );
});
