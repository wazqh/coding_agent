import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import type { TimelineItem } from "../state/store";
import { Timeline } from "./Timeline";

const items: TimelineItem[] = [
  { id: "u1", kind: "user", content: "修复验证逻辑" },
  {
    id: "a1",
    kind: "activity",
    activityId: "routine:1",
    activityKind: "workspace_check",
    title: "检查工作区",
    summary: "找到 3 处匹配",
    status: "completed",
    count: 3,
    detail: { hidden: "raw detail" },
  },
  {
    id: "m1",
    kind: "assistant",
    content:
      "## 完成\n\n测试已经通过。\n\n[查看文档](https://example.com/docs)\n\n![remote](https://example.com/a.png)",
    streaming: false,
  },
  {
    id: "v1",
    kind: "activity",
    activityId: "validation:1",
    activityKind: "validation",
    title: "运行测试",
    summary: "24 passed",
    status: "completed",
  },
  {
    id: "p1",
    kind: "approval",
    approvalId: "approval-1",
    action: "run_command",
    subject: "pytest -q",
    summary: "运行测试",
    resolved: false,
  },
];

test("renders user, compact activity, expanded markdown, and blocks remote images", () => {
  render(<Timeline items={items} onApproval={() => true} />);

  expect(screen.getByText("修复验证逻辑")).toBeInTheDocument();
  expect(screen.getByText("检查工作区")).toBeInTheDocument();
  expect(screen.getByText("找到 3 处匹配")).toBeInTheDocument();
  expect(screen.queryByText("raw detail")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "完成" })).toBeInTheDocument();
  expect(screen.getByText("验证通过")).toBeInTheDocument();
  expect(screen.getByText("24 passed")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "允许一次" })).toBeInTheDocument();
});

test("keeps a command approval summary concise without repeating the command", () => {
  const command = "python -c \"print('a very long command')\"";
  const approval: TimelineItem[] = [{
    id: "approval-command-summary",
    kind: "approval",
    approvalId: "approval-command-summary",
    action: "run_command",
    subject: command,
    summary: `run command in D:\\workspaces\\demo: ${command}`,
    resolved: false,
  }];

  render(<Timeline items={approval} onApproval={() => true} />);

  expect(screen.getByText(command)).toBeInTheDocument();
  expect(screen.getByText("run command in D:\\workspaces\\demo")).toBeInTheDocument();
  expect(screen.queryByText(`run command in D:\\workspaces\\demo: ${command}`)).not.toBeInTheDocument();
});

test("uses separate user and agent lanes with one grouped execution trace", () => {
  const laneItems: TimelineItem[] = [
    { id: "lane-user", kind: "user", content: "update the README" },
    {
      id: "lane-plan",
      kind: "plan",
      steps: [{ step: "Read the file", status: "in_progress" }],
    },
    items[1],
    { id: "lane-assistant", kind: "assistant", content: "Done.", streaming: false },
  ];
  const view = render(<Timeline items={laneItems} onApproval={() => true} />);

  expect(screen.getByText("update the README").closest("article")).toHaveClass("user-turn");
  expect(screen.getByText("Done.").closest("article")).toHaveClass("assistant-turn");
  const trace = view.container.querySelector(".execution-trace");
  expect(trace).toContainElement(screen.getByRole("button", { name: /计划未闭环/ }));
  expect(trace).toContainElement(screen.getByText("检查工作区").closest(".activity-row"));
  expect(view.container.querySelector(".section-rule")).toBeNull();
});

test("renders complete tool details as labeled fields without raw JSON", async () => {
  const user = userEvent.setup();
  const view = render(<Timeline items={[items[1]]} onApproval={() => true} showRaw />);

  expect(screen.getByText("hidden")).toBeInTheDocument();
  expect(screen.getByText("raw detail")).toBeInTheDocument();
  expect(view.container.querySelector(".activity-detail")).toBeNull();
  expect(view.container.textContent).not.toContain('{"hidden"');
  await user.click(screen.getByRole("button", { name: /检查工作区/ }));
});

test("expands an Agent note as rendered Markdown", async () => {
  const user = userEvent.setup();
  const note: TimelineItem[] = [{
    id: "agent-note",
    kind: "activity",
    activityId: "agent-note:1",
    activityKind: "agent_note",
    title: "Agent 说明",
    summary: "先检查实现，再补回归测试。",
    status: "completed",
    detail: { markdown: "## 排查结果\n\n**先检查实现**，再补回归测试。\n\n- 已定位到 `controller.py`" },
  }];

  const view = render(<Timeline items={note} onApproval={() => true} />);
  expect(screen.queryByRole("heading", { name: "排查结果" })).not.toBeInTheDocument();
  expect(screen.getByText("先检查实现，再补回归测试。")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Agent 说明/ }));

  expect(screen.getByRole("heading", { name: "排查结果" })).toBeInTheDocument();
  expect(screen.getByText("先检查实现")).toHaveStyle({ fontWeight: "bold" });
  expect(screen.getByText("controller.py")).toBeInTheDocument();
  expect(screen.queryByText("先检查实现，再补回归测试。")).not.toBeInTheDocument();
  expect(view.container.querySelector(".kind-agent_note .activity-note-detail")).toBeInTheDocument();
});

test("shows the current plan step and its neighboring steps while work is active", () => {
  const plan: TimelineItem[] = [
    {
      id: "plan-1",
      kind: "plan",
      steps: [
        { step: "检查工作区", status: "completed" },
        { step: "2. 修改实现", status: "in_progress" },
        { step: "运行测试", status: "pending" },
      ],
    },
  ];
  render(
    <Timeline
      items={plan}
      working={{ status: "executing", step: 2, maxSteps: 40, contextLeft: 80 }}
      onApproval={() => true}
    />,
  );

  expect(screen.getByText("正在按计划执行")).toBeInTheDocument();
  expect(screen.getByText("第 2/3 步 · 修改实现")).toBeInTheDocument();
  expect(screen.getByText("修改实现")).toBeInTheDocument();
  expect(screen.queryByText("2. 修改实现")).not.toBeInTheDocument();
  expect(screen.getByText("检查工作区")).toBeInTheDocument();
  expect(screen.getByText("运行测试")).toBeInTheDocument();
  expect(screen.getByText("1/3")).toBeInTheDocument();
});

test("labels an unfinished restored plan as incomplete instead of active work", () => {
  const plan: TimelineItem[] = [
    {
      id: "plan-history",
      kind: "plan",
      steps: [
        { step: "检查工作区", status: "completed" },
        { step: "修改实现", status: "in_progress" },
        { step: "运行测试", status: "pending" },
      ],
    },
  ];

  render(<Timeline items={plan} onApproval={() => true} />);

  expect(screen.getByText("计划未闭环")).toBeInTheDocument();
  expect(screen.getByText("已完成 1/3 步 · 停在：修改实现")).toBeInTheDocument();
  expect(screen.queryByText("正在按计划执行")).not.toBeInTheDocument();
});

test("renders live work progress at the end of the execution timeline", () => {
  render(
    <Timeline
      items={[items[0], items[1]]}
      working={{ status: "executing", step: 3, maxSteps: 40, contextLeft: 82 }}
      onApproval={() => true}
    />,
  );

  const feed = screen.getByRole("feed", { name: "Agent 执行记录" });
  const progress = within(feed).getByRole("status", { name: "当前执行状态" });
  expect(within(progress).getByText("正在执行")).toBeInTheDocument();
  expect(within(progress).getByText("· step 3/40 · 82% context left")).toBeInTheDocument();
  expect(progress).toHaveAttribute("data-status", "executing");
  const motion = progress.querySelector(".working-motion");
  expect(motion).toHaveAttribute("aria-hidden", "true");
  expect(motion?.querySelectorAll("i")).toHaveLength(3);
  expect(feed.lastElementChild).toBe(progress);
});

test("collapses a completed plan to its summary until the user expands it", async () => {
  const user = userEvent.setup();
  const plan: TimelineItem[] = [
    {
      id: "plan-complete",
      kind: "plan",
      steps: [
        { step: "检查工作区", status: "completed" },
        { step: "修改实现", status: "completed" },
        { step: "运行测试", status: "completed" },
      ],
    },
  ];
  render(<Timeline items={plan} onApproval={() => true} />);

  expect(screen.getByText("共 3 步")).toBeInTheDocument();
  const summary = screen.getByRole("button", { name: /计划已完成/ });
  expect(summary).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("检查工作区")).not.toBeInTheDocument();

  await user.click(summary);

  expect(screen.getByText("检查工作区")).toBeInTheDocument();
  expect(screen.getByText("修改实现")).toBeInTheDocument();
  expect(screen.getByText("运行测试")).toBeInTheDocument();
});

test("shows grouped workspace actions as an ordered execution trace", () => {
  const trace: TimelineItem[] = [
    {
      id: "workspace-trace",
      kind: "activity",
      activityId: "routine:1",
      activityKind: "workspace_check",
      title: "检查工作区",
      summary: "完成 3 项检查",
      status: "completed",
      count: 3,
      detail: {
        steps: [
          { name: "read_file", subject: "读取 README.md", status: "completed", summary: "读取 40 行" },
          { name: "search_text", subject: "搜索 RuntimeFactory", status: "completed", summary: "找到 2 处" },
          { name: "read_file", subject: "读取 pyproject.toml", status: "completed", summary: "读取 80 行" },
        ],
      },
    },
  ];
  render(<Timeline items={trace} onApproval={() => true} />);

  const list = screen.getByRole("list", { name: "检查工作区执行步骤" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(3);
  expect(within(list).getByText("读取 README.md")).toBeInTheDocument();
  expect(within(list).getByText("搜索 RuntimeFactory")).toBeInTheDocument();
  expect(within(list).getByText("读取 pyproject.toml")).toBeInTheDocument();
});

test("approval buttons send only the opaque id and disable after acceptance", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn(() => true);
  render(<Timeline items={items} onApproval={onApproval} />);

  await user.click(screen.getByRole("button", { name: "本会话允许" }));

  expect(onApproval).toHaveBeenCalledWith("approval-1", "allow_session");
  expect(screen.getByRole("button", { name: "允许一次" })).toBeDisabled();
});

test("submits allow-once only once on a double click", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn(() => true);
  render(<Timeline items={items} onApproval={onApproval} />);

  await user.dblClick(screen.getByRole("button", { name: "允许一次" }));

  expect(onApproval).toHaveBeenCalledOnce();
  expect(onApproval).toHaveBeenCalledWith("approval-1", "allow_once");
});

test("submits an explicit deny decision", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn(() => true);
  render(<Timeline items={items} onApproval={onApproval} />);

  await user.click(screen.getByRole("button", { name: "拒绝" }));

  expect(onApproval).toHaveBeenCalledWith("approval-1", "deny");
});

test("shows an inline diff before approving a proposed file edit", async () => {
  const user = userEvent.setup();
  const approvalWithDiff: TimelineItem[] = [
    {
      ...items[4],
      diff: "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-old\n+new\n",
    } as TimelineItem,
  ];
  const view = render(<Timeline items={approvalWithDiff} onApproval={() => true} />);

  expect(screen.queryByText("+new")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "查看拟议变更" }));
  expect(screen.getByText("new")).toBeInTheDocument();
  expect(view.container.querySelector(".diff-code-insert")).not.toBeNull();
  expect(view.container.querySelector(".diff-code-delete")).not.toBeNull();
});

test.each([
  ["allow_once", "已允许一次"],
  ["allow_session", "本会话已允许"],
  ["deny", "已拒绝"],
])("localizes a resolved approval decision %s", (decision, label) => {
  const resolvedItems: TimelineItem[] = [
    { ...items[4], resolved: true, decision } as TimelineItem,
  ];

  render(<Timeline items={resolvedItems} onApproval={() => true} />);

  expect(screen.queryByText("需要批准")).not.toBeInTheDocument();
  expect(screen.getByText(label)).toBeInTheDocument();
  expect(screen.queryByText(decision)).not.toBeInTheDocument();
});

test("keeps approval controls active when transport rejects the request", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn(() => false);
  render(<Timeline items={items} onApproval={onApproval} />);

  await user.click(screen.getByRole("button", { name: "允许一次" }));

  expect(onApproval).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "允许一次" })).toBeEnabled();
});

test("uses a human-readable label for verification registration approvals", () => {
  const registration = {
    ...items[4],
    action: "register_verification",
    subject: "algorithm_practice: python -m pytest tests -q",
    summary: "register verification: Algorithm tests",
  } as TimelineItem;

  render(<Timeline items={[registration]} onApproval={() => true} />);

  expect(screen.getByText("注册验证规则")).toBeInTheDocument();
  expect(screen.queryByText("register_verification")).not.toBeInTheDocument();
});

test("keeps a backend-cancelled approval permanently resolved after reconnect", async () => {
  const user = userEvent.setup();
  const onApproval = vi.fn(() => true);
  const resolvedItems: TimelineItem[] = [
    { ...items[4], resolved: true, decision: "cancelled" } as TimelineItem,
  ];
  const view = render(
    <Timeline items={items} onApproval={onApproval} approvalAvailable />,
  );
  await user.click(screen.getByRole("button", { name: "允许一次" }));
  expect(screen.getByRole("button", { name: "允许一次" })).toBeDisabled();

  view.rerender(<Timeline items={resolvedItems} onApproval={onApproval} approvalAvailable={false} />);
  view.rerender(<Timeline items={resolvedItems} onApproval={onApproval} approvalAvailable />);

  expect(screen.queryByRole("button", { name: "允许一次" })).not.toBeInTheDocument();
  expect(screen.getByText("已取消")).toBeInTheDocument();
});

test("keeps unverified completion neutral and reserves success language for real validation", () => {
  const completions: TimelineItem[] = [
    {
      id: "done-unverified",
      kind: "completion",
      turnId: "turn-unverified",
      status: "completed",
      reason: "",
      validationStatus: "not_run",
    },
    {
      id: "done-verified",
      kind: "completion",
      status: "completed",
      reason: "",
      validationStatus: "passed",
    },
  ];
  const onVerify = vi.fn();
  render(<Timeline items={completions} onApproval={() => true} onVerify={onVerify} />);

  expect(screen.getByText("已结束 · 未验证")).toBeInTheDocument();
  expect(screen.getByText("已完成 · 验证通过")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "验证此轮" })).toBeInTheDocument();
});

test("shows a plain completion without verification controls for a read-only turn", () => {
  const onVerify = vi.fn();
  const completion: TimelineItem[] = [{
    id: "done-read-only",
    kind: "completion",
    turnId: "turn-read-only",
    status: "completed",
    reason: "assistant completed",
    validationStatus: "not_needed",
  }];

  render(<Timeline items={completion} onApproval={() => true} onVerify={onVerify} />);

  expect(screen.getByText("已完成")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "验证此轮" })).not.toBeInTheDocument();
  expect(screen.queryByText("未验证")).not.toBeInTheDocument();
});

test("offers repair for a failed verification with the failed turn id", async () => {
  const user = userEvent.setup();
  const onRepair = vi.fn();
  const failed: TimelineItem[] = [
    {
      id: "done-failed-verification",
      kind: "completion",
      turnId: "turn-failed",
      status: "completed",
      reason: "verification failed after two repair attempts",
      validationStatus: "failed",
    },
  ];
  render(<Timeline items={failed} onApproval={() => true} onRepair={onRepair} />);

  expect(screen.getByText("已完成 · 验证失败")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "修复验证失败" }));
  expect(onRepair).toHaveBeenCalledWith("turn-failed");
});

test("uses precise recovery actions for verification configuration and timeouts", async () => {
  const user = userEvent.setup();
  const onConfigureVerification = vi.fn();
  const onVerify = vi.fn();
  const exact: TimelineItem[] = [
    {
      id: "config-error",
      kind: "completion",
      turnId: "turn-config",
      status: "completed",
      reason: "",
      validationStatus: "failed",
      verificationStatus: "configuration_error",
    },
    {
      id: "timeout",
      kind: "completion",
      turnId: "turn-timeout",
      status: "completed",
      reason: "",
      validationStatus: "failed",
      verificationStatus: "timed_out",
    },
  ];

  render(
    <Timeline
      items={exact}
      onApproval={() => true}
      onVerify={onVerify}
      onConfigureVerification={onConfigureVerification}
    />,
  );

  expect(screen.getByText("已结束 · 验证配置有误")).toBeInTheDocument();
  expect(screen.getByText("已结束 · 验证超时")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "修复验证配置" }));
  await user.click(screen.getByRole("button", { name: "重新验证此轮" }));
  expect(onConfigureVerification).toHaveBeenCalledOnce();
  expect(onVerify).toHaveBeenCalledWith("turn-timeout");
});

test("marks a user message after a completion as the start of a new turn", () => {
  const turns: TimelineItem[] = [
    {
      id: "done-1",
      kind: "completion",
      status: "completed",
      reason: "",
      validationStatus: "not_run",
    },
    { id: "user-2", kind: "user", content: "continue with the next task" },
  ];

  render(<Timeline items={turns} onApproval={() => true} />);

  expect(screen.getByText("continue with the next task").closest("article")).toHaveClass(
    "starts-new-turn",
  );
});

test("renders a failed turn as failed even when no validation ran", () => {
  const failed: TimelineItem[] = [
    {
      id: "done-failed",
      kind: "completion",
      status: "failed",
      reason: "model error",
      validationStatus: "not_run",
    },
  ];
  render(<Timeline items={failed} onApproval={() => true} />);

  expect(screen.getByText("执行失败 · 未运行验证")).toBeInTheDocument();
  expect(screen.queryByText(/已完成/)).not.toBeInTheDocument();
});

test("failed validation output is expandable", async () => {
  const user = userEvent.setup();
  const failed: TimelineItem[] = [
    {
      id: "v2",
      kind: "activity",
      activityId: "validation:2",
      activityKind: "validation",
      title: "运行验证",
      summary: "1 failed",
      status: "failed",
      detail: { data: { output: "AssertionError: expected 2" } },
    },
  ];
  render(<Timeline items={failed} onApproval={() => true} />);

  await user.click(screen.getByRole("button", { name: "展开失败输出" }));
  expect(screen.getByText(/AssertionError: expected 2/)).toBeInTheDocument();
});

test("shows a blocked command as a readable safety explanation instead of raw JSON", async () => {
  const user = userEvent.setup();
  const blocked: TimelineItem[] = [
    {
      id: "command-blocked",
      kind: "activity",
      activityId: "command:blocked",
      activityKind: "command",
      title: "已阻止高风险命令",
      summary: "强制清理 Git 工作区",
      status: "failed",
      detail: {
        ok: false,
        code: "DANGEROUS_COMMAND",
        summary: "command matches a destructive safety rule",
        data: {
          command: "git clean -fd",
          hard_blocked: true,
          rule_id: "git-clean-force",
          risk_label: "强制清理 Git 工作区",
          matched_text: "git clean -fd",
          guidance: "先查看 git status 和 git clean -nd，再让用户确认精确目标。",
        },
      },
    },
  ];
  const view = render(<Timeline items={blocked} onApproval={() => true} />);

  await user.click(screen.getByRole("button", { name: /已阻止高风险命令/ }));

  expect(screen.getByText("已阻止", { selector: ".activity-heading i" })).toBeInTheDocument();
  expect(screen.getByText("已阻止高风险操作")).toBeInTheDocument();
  expect(screen.getByText("硬安全规则")).toBeInTheDocument();
  expect(screen.getAllByText("强制清理 Git 工作区")).toHaveLength(2);
  expect(screen.getByText(/先查看 git status/)).toBeInTheDocument();
  expect(screen.getByText("命令已在执行前停止，未对工作区产生改动。")).toBeInTheDocument();
  expect(view.container.querySelector(".hard-block-shield")).toBeInTheDocument();
  expect(view.container.querySelector(".activity-status")?.textContent).not.toContain("×");
  expect(view.container.querySelector(".safety-command mark")).toHaveTextContent("git clean -fd");
  expect(screen.queryByText("DANGEROUS_COMMAND")).not.toBeInTheDocument();
  expect(view.container.querySelector(".activity-detail")).toBeNull();
});

test("asks before opening an external link", async () => {
  const user = userEvent.setup();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const open = vi.spyOn(window, "open").mockImplementation(() => null);
  render(<Timeline items={items} onApproval={() => true} />);

  await user.click(screen.getByRole("link", { name: "查看文档" }));

  expect(confirm).toHaveBeenCalledWith("是否打开外部链接？\nhttps://example.com/docs");
  expect(open).not.toHaveBeenCalled();
  confirm.mockRestore();
  open.mockRestore();
});
