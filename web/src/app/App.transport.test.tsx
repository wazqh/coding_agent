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

test("opens inspector command records in the conversation-side detail pane", async () => {
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
      data: { busy: false, model: "gemini-flash", permissions: "prompt" },
    });
    transport.emit({
      protocol_version: 2,
      type: "activity.upsert",
      seq: 2,
      session_id: "a".repeat(24),
      turn_id: "turn-1",
      data: {
        activity_id: "command-1",
        kind: "command",
        title: "运行命令",
        summary: "command exited with code 0",
        status: "completed",
        detail: {
          code: "OK",
          data: { command: "python -m pytest -q", cwd: ".", exit_code: 0, stdout: "2 passed" },
        },
      },
    });
  });

  await user.click(screen.getByRole("button", { name: "任务检查器" }));
  await user.click(screen.getByRole("tab", { name: "运行" }));
  const drawer = screen.getByRole("complementary", { name: "任务检查器" });
  expect(within(drawer).queryByText("python -m pytest -q")).not.toBeInTheDocument();
  await user.click(within(drawer).getByRole("button", { name: /查看命令详情/ }));

  expect(screen.getByRole("dialog", { name: "命令执行详情" })).toBeInTheDocument();
  expect(screen.getByText("python -m pytest -q")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "关闭执行详情" }));
  expect(screen.queryByRole("dialog", { name: "命令执行详情" })).not.toBeInTheDocument();
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
          steps: { current: 40, minimum: 30, maximum: 999, overridden: false },
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
          steps: { current: 40, minimum: 30, maximum: 999, overridden: true },
        },
      },
    });
  });
  expect(await screen.findByRole("status", { name: "最大步骤保存状态" }))
    .toHaveTextContent("已保存，下一轮任务生效");
});

test("separates command history from verification settings and saves its mode", async () => {
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
          steps: { current: 40, minimum: 30, maximum: 999, overridden: false },
          verification: {
            mode: "agent_tdd",
            enabled: true,
            agent_tdd: true,
            checks: [{
              id: "python-tests",
              label: "Python tests",
              kind: "test",
              command: "python -m pytest -q",
              cwd: ".",
              timeout_seconds: 120,
              enabled: true,
            }],
            commands: ["python -m pytest -q"],
            suggestions: [{
              id: "suggested-ruff",
              label: "Ruff",
              kind: "lint",
              command: "python -m ruff check .",
              cwd: ".",
              timeout_seconds: 120,
              enabled: true,
              target_paths: ["."],
              scope: "full_project",
            }],
            procedures: [{
              id: "dependency-regression",
              instruction: "依赖变化后重跑原有规则。",
              enabled: true,
            }],
          },
        },
      },
    });
  });

  expect(screen.getByRole("tab", { name: "命令记录" })).toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "验证" }));
  expect(screen.getByRole("radio", { name: /Agent TDD/ })).toHaveAttribute("aria-checked", "true");
  const procedureHeading = screen.getByRole("heading", { name: "检验规程" });
  const ruleHeading = screen.getByRole("heading", { name: "Agent 验证规则" });
  expect(procedureHeading.compareDocumentPosition(ruleHeading) & Node.DOCUMENT_POSITION_FOLLOWING)
    .toBeTruthy();
  const input = screen.getByRole("textbox", { name: "验证命令 1" });
  const cwd = screen.getByRole("textbox", { name: "工作目录 1" });
  const timeout = screen.getByRole("spinbutton", { name: "超时秒数 1" });
  expect(input).toHaveValue("python -m pytest -q");
  expect(cwd).toHaveValue(".");
  expect(timeout).toHaveValue(120);
  expect(screen.queryByRole("button", { name: "添加建议命令 python -m ruff check ." }))
    .not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "添加规则" }));
  expect(screen.getByRole("button", { name: "添加建议命令 python -m ruff check ." }))
    .toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "检验规程 1" }))
    .toHaveValue("依赖变化后重跑原有规则。");
  expect(screen.queryByRole("spinbutton", { name: "最大步骤" })).not.toBeInTheDocument();
  expect(screen.queryByRole("combobox", { name: "当前模型" })).not.toBeInTheDocument();
  await user.clear(input);
  await user.type(input, "python -m pytest tests -q");
  await user.clear(cwd);
  await user.type(cwd, "algorithm_practice");
  await user.clear(timeout);
  await user.type(timeout, "90");
  await user.click(screen.getByRole("button", { name: "保存验证设置" }));

  expect(transport.request).toHaveBeenCalledWith("verification.set", {
    mode: "agent_tdd",
    checks: [{
      id: "python-tests",
      label: "Python tests",
      kind: "test",
      command: "python -m pytest tests -q",
      cwd: "algorithm_practice",
      timeout_seconds: 90,
      enabled: true,
      target_paths: [],
    }],
    procedures: [{
      id: "dependency-regression",
      instruction: "依赖变化后重跑原有规则。",
      enabled: true,
    }],
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
          steps: { current: 40, minimum: 30, maximum: 999, overridden: false },
          verification: {
            mode: "agent_tdd",
            enabled: true,
            agent_tdd: true,
            checks: [{
              id: "python-tests",
              label: "Python tests",
              kind: "test",
              command: "python -m pytest tests -q",
              cwd: "algorithm_practice",
              timeout_seconds: 90,
              enabled: true,
            }],
            commands: ["python -m pytest tests -q"],
            procedures: [{
              id: "dependency-regression",
              instruction: "依赖变化后重跑原有规则。",
              enabled: true,
            }],
          },
        },
      },
    });
  });
  expect(await screen.findByRole("status")).toHaveTextContent("验证设置已保存到当前会话");
});

test("allows choosing Agent TDD before a verification command is configured", async () => {
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
          steps: { current: 40, minimum: 30, maximum: 999, overridden: false },
          verification: {
            mode: "off",
            enabled: false,
            agent_tdd: false,
            commands: [],
            suggestions: [],
          },
        },
      },
    });
  });

  await user.click(screen.getByRole("tab", { name: "验证" }));
  expect(screen.queryByRole("heading", { name: "验证规则" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "检验规程" })).not.toBeInTheDocument();
  expect(screen.getByText("关闭后不会在回合结束时自动执行命令。"))
    .toBeInTheDocument();
  const tdd = screen.getByRole("radio", { name: /Agent TDD/ });
  expect(tdd).toBeEnabled();
  await user.click(tdd);
  expect(tdd).toHaveAttribute("aria-checked", "true");
  expect(screen.getByRole("heading", { name: "检验规程" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Agent 验证规则" })).toBeInTheDocument();
  expect(screen.getByText("先告诉 Agent 何时需要新增、重跑或收紧测试，再由它登记可执行规则。"))
    .toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "保存验证设置" }));
  expect(transport.request).toHaveBeenCalledWith("verification.set", {
    mode: "agent_tdd",
    checks: [],
    procedures: [],
  });
});

test("turns verification off without hidden incomplete drafts blocking save", async () => {
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
          steps: { current: 40, minimum: 30, maximum: 999, overridden: false },
          verification: {
            mode: "off",
            enabled: false,
            agent_tdd: false,
            checks: [],
            commands: [],
            suggestions: [],
            procedures: [],
          },
        },
      },
    });
  });

  await user.click(screen.getByRole("button", { name: "任务检查器" }));
  await user.click(screen.getByRole("tab", { name: "运行" }));
  await user.click(screen.getByRole("tab", { name: "验证" }));
  await user.click(screen.getByRole("radio", { name: /Agent TDD/ }));
  await user.click(screen.getByRole("button", { name: "添加规程" }));
  await user.click(screen.getByRole("button", { name: "添加规则" }));
  await user.click(screen.getByRole("button", { name: "添加空白规则" }));
  await user.click(screen.getByRole("radio", { name: /关闭/ }));
  await user.click(screen.getByRole("button", { name: "保存验证设置" }));

  expect(transport.request).toHaveBeenCalledWith("verification.set", {
    mode: "off",
    checks: [],
    procedures: [],
  });
  expect(screen.queryByText("请补全每条验证规则的名称和命令")).not.toBeInTheDocument();
  expect(screen.queryByText("请补全检验规程内容，或删除空白规程")).not.toBeInTheDocument();
});

test("shows the source and coverage of an Agent-registered verification rule", async () => {
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
          verification: {
            enabled: true,
            agent_tdd: true,
            checks: [{
              id: "agent-algorithm-tests",
              label: "Algorithm tests",
              kind: "test",
              command: "python -m pytest tests -q",
              cwd: "algorithm_practice",
              timeout_seconds: 90,
              enabled: true,
              source: "agent",
              target_paths: ["algorithm_practice"],
            }],
          },
        },
      },
    });
  });

  await user.click(screen.getByRole("tab", { name: "验证" }));
  expect(screen.getByText("Agent 登记")).toBeInTheDocument();
  expect(screen.getByText("覆盖 algorithm_practice")).toBeInTheDocument();
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
  expect(screen.getByLabelText("src/demo.py 的变更")).toHaveTextContent("hello");

  await user.click(screen.getByRole("button", { name: "撤销改动" }));
  expect(transport.request).toHaveBeenCalledWith("change.review", {
    change_id: "a".repeat(32),
    decision: "discard",
  });
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

  expect(screen.getByRole("dialog", { name: "src/demo.py 文件预览" })).toHaveTextContent(
    "def demo():",
  );
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

  await user.click(screen.getByRole("button", { name: "从 Forge 移除项目 demo" }));
  const dialog = screen.getByRole("alertdialog", { name: "移除项目demo" });
  expect(dialog).toHaveTextContent("D:\\codes\\demo");
  expect(dialog).toHaveTextContent("不会删除工作区文件、Git 数据、会话或 Memory");
  await user.click(
    within(dialog).getByRole("button", { name: "确认从 Forge 移除 demo" }),
  );

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
  expect(screen.getByText("模型列表")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "完成" }));
  expect(screen.getByRole("combobox", { name: "当前模型" })).toBeInTheDocument();
});

test("copies a model inside its existing provider without copying its credential", async () => {
  const user = userEvent.setup();
  const transport = new FakeTransport();
  const copyProviderCredential = vi.fn(async () => ({
    persisted: true,
    backend: "os-credential-copy",
    transactionId: "copy-transaction",
  }));
  Object.defineProperty(window, "forgeDesktop", {
    configurable: true,
    value: {
      runtimeInfo: vi.fn(),
      selectWorkspace: vi.fn(),
      saveProviderCredential: vi.fn(),
      copyProviderCredential,
      commitProviderCredential: vi.fn(async () => true),
      rollbackProviderCredential: vi.fn(async () => true),
      deleteProviderCredential: vi.fn(async () => undefined),
      restartGateway: vi.fn(async () => undefined),
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
            base_url: "https://open.bigmodel.cn/api/paas/v4",
            default_model: "glm-5.3-flash",
            models: ["glm-5.3-flash"],
            managed: true,
            active: true,
          }],
        },
      },
    });
  });

  await user.type(screen.getByRole("textbox", { name: "任务输入" }), "/model{Enter}");
  await user.click(screen.getByRole("button", { name: "管理连接" }));
  await user.click(screen.getByRole("button", { name: "复制 GLM / glm-5.3-flash" }));

  expect(screen.getByLabelText("服务商名称")).toHaveValue("GLM");
  expect(screen.getByLabelText("Model ID")).toHaveValue("");
  await user.type(screen.getByLabelText("Model ID"), "glm-5.2-flash");
  await user.click(screen.getByRole("button", { name: "保存模型" }));

  expect(copyProviderCredential).not.toHaveBeenCalled();
  expect(transport.request).toHaveBeenCalledWith("model.provider.upsert", {
    provider: "GLM",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-5.2-flash",
    compatibility: "openai",
  });
  Reflect.deleteProperty(window, "forgeDesktop");
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
  await user.click(screen.getByRole("button", { name: "添加模型" }));
  await user.type(await screen.findByLabelText("Model ID"), "vendor/fast-model");
  await user.type(screen.getByLabelText("API Key"), "top-secret");
  await user.click(screen.getByRole("button", { name: "保存模型" }));

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
  await user.click(screen.getByRole("button", { name: "添加模型" }));
  await user.type(await screen.findByLabelText("Model ID"), "vendor/fast-model");
  await user.type(screen.getByLabelText("API Key"), "top-secret");
  await user.click(screen.getByRole("button", { name: "保存模型" }));
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
  expect(screen.getByText("正在打开目录选择器…")).toBeInTheDocument();

  resolveSelection("D:\\codes\\selected-project");
  await waitFor(() =>
    expect(restartGateway).toHaveBeenCalledWith({ workspace: "D:\\codes\\selected-project" }),
  );
  act(() => transport.emitStatus("disconnected"));
  expect(screen.getByRole("status", { name: "正在切换项目" })).toBeInTheDocument();
  expect(screen.queryByRole("alert", { name: "无法连接本地 Agent" })).not.toBeInTheDocument();
  await act(async () => {
    finishRestart();
    await Promise.resolve();
  });
});
