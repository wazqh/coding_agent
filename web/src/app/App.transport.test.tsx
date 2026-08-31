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

  expect(screen.getByRole("status", { name: "正在启动本地 Agent" })).toBeInTheDocument();
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
  expect(screen.queryByRole("status", { name: "正在启动本地 Agent" })).not.toBeInTheDocument();
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

test("confirms a maximum-step update after the runtime snapshot applies it", async () => {
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
      data: { busy: false, model: "gemini-flash", permissions: "prompt" },
    });
  });
  await user.click(screen.getByRole("button", { name: "任务检查器" }));
  await user.click(screen.getByRole("tab", { name: "设置" }));
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "runtime.updated",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        runtime: {
          workspace_name: "coding_agent",
          workspace: "D:\\codes\\coding_agent",
          permissions: "prompt",
          model: { id: "gemini-flash" },
          context: { estimated_tokens: 0, context_window: 100000, percent_used: 0 },
          steps: { current: 12, minimum: 12, maximum: 100, overridden: false },
        },
      },
    });
  });

  const input = screen.getByRole("spinbutton", { name: "最大步骤" });
  await user.clear(input);
  await user.type(input, "40");
  await user.click(screen.getByRole("button", { name: "保存" }));

  expect(transport.request).toHaveBeenCalledWith("steps.set", { value: 40 });
  expect(screen.getByRole("button", { name: "保存中…" })).toBeDisabled();
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "runtime.updated",
      seq: 3,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        runtime: {
          workspace_name: "coding_agent",
          workspace: "D:\\codes\\coding_agent",
          permissions: "prompt",
          model: { id: "gemini-flash" },
          context: { estimated_tokens: 0, context_window: 100000, percent_used: 0 },
          steps: { current: 40, minimum: 12, maximum: 100, overridden: true },
        },
      },
    });
  });
  expect(await screen.findByRole("status", { name: "最大步骤保存状态" }))
    .toHaveTextContent("已保存，下一轮任务生效");
});

test("configures project verification commands from the run inspector", async () => {
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
      data: { busy: false, model: "gemini-flash", permissions: "prompt" },
    });
  });
  await user.click(screen.getByRole("button", { name: "任务检查器" }));
  await user.click(screen.getByRole("tab", { name: "运行" }));
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "runtime.updated",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        runtime: {
          workspace_name: "coding_agent",
          workspace: "D:\\codes\\coding_agent",
          permissions: "prompt",
          model: { id: "gemini-flash" },
          context: { estimated_tokens: 0, context_window: 100000, percent_used: 0 },
          steps: { current: 12, minimum: 12, maximum: 100, overridden: false },
          verification: { commands: ["python -m pytest -q"] },
        },
      },
    });
  });

  const input = screen.getByRole("textbox", { name: "项目验证命令" });
  expect(input).toHaveValue("python -m pytest -q");
  expect(screen.queryByRole("spinbutton", { name: "最大步骤" })).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "当前模型" })).not.toBeInTheDocument();
  await user.clear(input);
  await user.type(input, "python -m ruff check .{Enter}python -m pytest -q");
  await user.click(screen.getByRole("button", { name: "保存验证规则" }));

  expect(transport.request).toHaveBeenCalledWith("verification.set", {
    commands: ["python -m ruff check .", "python -m pytest -q"],
  });
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "runtime.updated",
      seq: 3,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        runtime: {
          workspace_name: "coding_agent",
          workspace: "D:\\codes\\coding_agent",
          permissions: "prompt",
          model: { id: "gemini-flash" },
          context: { estimated_tokens: 0, context_window: 100000, percent_used: 0 },
          steps: { current: 12, minimum: 12, maximum: 100, overridden: false },
          verification: {
            commands: ["python -m ruff check .", "python -m pytest -q"],
          },
        },
      },
    });
  });
  expect(await screen.findByRole("status")).toHaveTextContent("验证规则已保存");
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
  await user.click(screen.getByRole("button", { name: "修复测试的更多操作" }));
  await user.click(screen.getByRole("menuitem", { name: "删除对话" }));
  await user.click(screen.getByRole("button", { name: "确认删除修复测试" }));
  await user.click(screen.getByRole("button", { name: "任务检查器" }));

  expect(transport.request).toHaveBeenCalledWith("session.create");
  expect(transport.request).toHaveBeenCalledWith("session.resume", {
    session_id: "b".repeat(24),
  });
  expect(transport.request).toHaveBeenCalledWith("session.delete", {
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
            id: "a".repeat(32),
            path: "src/demo.py",
            kind: "created",
            reversible: true,
            additions: 1,
            deletions: 0,
            diff: "--- a/src/demo.py\n+++ b/src/demo.py\n@@ -0,0 +1 @@\n+hello\n",
          },
        ],
      },
    });
  });

  const changeRow = await screen.findByRole("button", { name: /src\/demo.py/ });
  expect(screen.queryByLabelText("src/demo.py 的变更")).not.toBeInTheDocument();
  expect(screen.queryByText("hello")).not.toBeInTheDocument();

  await user.click(changeRow);
  expect(screen.getByLabelText("src/demo.py 的变更")).toBeInTheDocument();
  expect(screen.getByText("hello")).toBeInTheDocument();
  await user.click(changeRow);
  expect(screen.queryByLabelText("src/demo.py 的变更")).not.toBeInTheDocument();

  await user.click(changeRow);
  await user.click(screen.getByRole("button", { name: "查看文件" }));
  expect(transport.request).toHaveBeenCalledWith("file.preview", { path: "src/demo.py" });
  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "file.previewed",
      seq: 3,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        path: "src/demo.py",
        language: "python",
        size: 10,
        text: "full file\n",
      },
    });
  });
  const previewFrame = screen.getByLabelText("src/demo.py 的变更");
  expect(previewFrame).toHaveTextContent("full file");
  expect(screen.queryByLabelText("src/demo.py 文件预览")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "查看 Diff" }));
  expect(previewFrame).toHaveTextContent("hello");
  expect(previewFrame).not.toHaveTextContent("full file");

  await user.click(screen.getByRole("button", { name: "撤销此变更" }));
  await user.click(screen.getByRole("button", { name: "确认撤销" }));
  expect(transport.request).toHaveBeenCalledWith("change.undo", { change_id: "a".repeat(32) });
});

test("groups session files in a collapsible tree and previews the selected file", async () => {
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
      type: "changes.updated",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        changes: [
          {
            id: "a".repeat(32),
            path: "src/demo.py",
            kind: "modified",
            additions: 2,
            deletions: 1,
            diff: "--- a/src/demo.py\n+++ b/src/demo.py\n",
          },
          {
            id: "b".repeat(32),
            path: "src/nested/tool.ts",
            kind: "created",
            additions: 4,
            deletions: 0,
            diff: "--- /dev/null\n+++ b/src/nested/tool.ts\n",
          },
        ],
      },
    });
  });

  await user.click(screen.getByRole("button", { name: "任务检查器" }));
  await user.click(screen.getByRole("tab", { name: "资源" }));

  const tree = screen.getByRole("tree", { name: "会话文件" });
  const srcDirectory = within(tree).getByRole("treeitem", { name: "src 文件夹" });
  expect(within(tree).getByRole("treeitem", { name: "demo.py 已修改" })).toBeVisible();
  expect(within(tree).getByRole("treeitem", { name: "nested 文件夹" })).toBeVisible();

  await user.click(srcDirectory);
  expect(within(tree).queryByRole("treeitem", { name: "demo.py 已修改" })).not.toBeInTheDocument();
  await user.click(srcDirectory);
  await user.click(within(tree).getByRole("treeitem", { name: "demo.py 已修改" }));
  expect(transport.request).toHaveBeenCalledWith("file.preview", { path: "src/demo.py" });

  act(() => {
    transport.emit({
      protocol_version: 2,
      type: "file.previewed",
      seq: 3,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        path: "src/demo.py",
        language: "python",
        size: 18,
        text: "def demo():\n    pass\n",
      },
    });
  });

  expect(screen.getByLabelText("src/demo.py 文件预览")).toHaveTextContent("def demo():");
  expect(screen.getByText("python · 18 B · 只读")).toBeInTheDocument();
});

test("removes a recent project only after showing the exact safe scope", async () => {
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
      data: {
        workspace_name: "coding_agent",
        workspace_path: "D:\\codes\\coding_agent",
        model: "gemini-flash",
        permissions: "prompt",
        busy: false,
        projects: [
          {
            name: "coding_agent",
            path: "D:\\codes\\coding_agent",
            current: true,
            sessions: [],
          },
          {
            name: "demo",
            path: "D:\\codes\\demo",
            current: false,
            sessions: [],
          },
        ],
      },
    });
  });

  await user.click(screen.getByRole("button", { name: "移除项目 demo" }));
  const dialog = screen.getByRole("alertdialog", { name: "移除项目demo" });
  expect(dialog).toHaveTextContent("D:\\codes\\demo");
  expect(dialog).toHaveTextContent("不会删除工作目录、Git 文件、会话或 Memory");
  await user.click(within(dialog).getByRole("button", { name: "移除" }));

  expect(transport.request).toHaveBeenCalledWith("project.remove", {
    path: "D:\\codes\\demo",
  });
});

test("keeps daily model switching separate from connection management", async () => {
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
      data: {
        workspace_name: "coding_agent",
        workspace_path: "D:\\codes\\coding_agent",
        model: "glm-5.3-flash",
        permissions: "prompt",
        busy: false,
      },
    });
    transport.emit({
      protocol_version: 2,
      type: "model.catalog.updated",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: null,
      data: {
        catalog: {
          active: { provider: "GLM", id: "glm-5.3-flash" },
          providers: [{
            name: "GLM",
            default_model: "glm-5.3-flash",
            models: ["glm-5.2-flash", "glm-5.3-flash"],
            managed: true,
            active: true,
          }],
        },
      },
    });
  });

  await user.type(screen.getByRole("textbox", { name: "任务输入" }), "/model{Enter}");
  expect(screen.getByRole("combobox", { name: "当前模型" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "glm-5.2-flash · GLM" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "管理连接" }));
  expect(screen.queryByRole("combobox", { name: "当前模型" })).not.toBeInTheDocument();
  expect(screen.getByText("模型连接")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "完成" }));
  expect(screen.getByRole("combobox", { name: "当前模型" })).toBeInTheDocument();
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
  let finishRestart: () => void = () => undefined;
  const restartGateway = vi.fn(() => new Promise<void>((resolve) => {
    finishRestart = resolve;
  }));
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
  expect(screen.getByRole("tab", { name: "设置" })).toHaveAttribute("aria-selected", "true");
  await user.click(screen.getByRole("button", { name: "管理连接" }));
  await user.click(screen.getByRole("button", { name: "添加连接" }));
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
    probeModel: true,
  }));
  act(() => transport.emitStatus("disconnected"));
  expect(screen.getByRole("status", { name: "正在应用模型配置" })).toBeInTheDocument();
  expect(screen.queryByRole("alert", { name: "无法连接本地 Agent" })).not.toBeInTheDocument();
  act(() => finishRestart());
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
  await user.click(screen.getByRole("button", { name: "管理连接" }));
  await user.click(screen.getByRole("button", { name: "添加连接" }));
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
  let finishRestart: () => void = () => undefined;
  const restartGateway = vi.fn(() => new Promise<void>((resolve) => {
    finishRestart = resolve;
  }));
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
  act(() => transport.emitStatus("disconnected"));
  expect(screen.getByRole("status", { name: "正在切换项目" })).toBeInTheDocument();
  expect(screen.queryByRole("alert", { name: "无法连接本地 Agent" })).not.toBeInTheDocument();
  act(() => finishRestart());
});
