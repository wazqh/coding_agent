import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { SessionRail } from "./SessionRail";

const sessions = [
  {
    id: "a".repeat(24),
    title: "修复测试",
    updatedAt: "2026-08-29T10:00:00Z",
    model: "gemini-flash",
  },
];

const projects = [
  {
    name: "coding_agent",
    path: "D:\\codes\\coding_agent",
    current: true,
    sessions,
  },
  {
    name: "demo",
    path: "D:\\codes\\demo",
    current: false,
    sessions: [
      {
        id: "b".repeat(24),
        title: "整理文档",
        updatedAt: "2026-08-28T10:00:00Z",
        model: "deepseek-chat",
      },
    ],
  },
];

test("creates and resumes workspace sessions", async () => {
  const user = userEvent.setup();
  const onNewSession = vi.fn();
  const onResumeSession = vi.fn();
  render(
    <SessionRail
      productName="Forge"
      workspaceName="coding_agent"
      busy={false}
      open
      sessions={sessions}
      projects={projects}
      activeSessionId={null}
      onNewSession={onNewSession}
      onResumeSession={onResumeSession}
    />,
  );

  await user.click(screen.getByRole("button", { name: "新对话" }));
  await user.click(screen.getByRole("treeitem", { name: /修复测试/ }));

  expect(onNewSession).toHaveBeenCalledOnce();
  expect(onResumeSession).toHaveBeenCalledWith("a".repeat(24));
  expect(screen.queryByText("gemini-flash")).not.toBeInTheDocument();
  expect(screen.getByRole("treeitem", { name: /coding_agent/ })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  expect(screen.getByRole("treeitem", { name: /demo/ })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  expect(screen.queryByRole("treeitem", { name: /整理文档/ })).not.toBeInTheDocument();
});

test("locks session switching while the agent is busy", () => {
  render(
    <SessionRail
      productName="Forge"
      workspaceName="coding_agent"
      busy
      open
      sessions={sessions}
      projects={projects}
      activeSessionId={sessions[0].id}
      onNewSession={() => undefined}
      onResumeSession={() => undefined}
    />,
  );

  expect(screen.getByRole("button", { name: "新对话" })).toBeDisabled();
  expect(screen.getByRole("treeitem", { name: /修复测试/ })).toBeDisabled();
});

test("opens a non-current project when its project row is selected", async () => {
  const user = userEvent.setup();
  const onOpenProject = vi.fn();
  render(
    <SessionRail
      productName="Forge"
      workspaceName="coding_agent"
      busy={false}
      open
      sessions={sessions}
      projects={projects}
      activeSessionId={null}
      onNewSession={() => undefined}
      onResumeSession={() => undefined}
      onOpenProject={onOpenProject}
    />,
  );

  await user.click(screen.getByRole("treeitem", { name: "demo" }));

  expect(onOpenProject).toHaveBeenCalledWith("D:\\codes\\demo");
});

test("keeps the collapse control in the rail header and exposes project picker progress", () => {
  const { container } = render(
    <SessionRail
      productName="Forge"
      workspaceName="coding_agent"
      busy={false}
      open
      sessions={sessions}
      projects={projects}
      activeSessionId={null}
      addingProject
      projectFeedback="正在打开目录选择器…"
      onNewSession={() => undefined}
      onResumeSession={() => undefined}
    />,
  );

  const collapse = screen.getByRole("button", { name: "折叠会话栏" });
  expect(collapse.closest(".rail-header")).not.toBeNull();
  expect(screen.getByRole("button", { name: "正在添加项目" })).toHaveAttribute(
    "aria-busy",
    "true",
  );
  expect(screen.getByRole("status")).toHaveTextContent("正在打开目录选择器…");
  expect(container.querySelector(".project-tree-heading")).toContainElement(
    screen.getByRole("button", { name: "正在添加项目" }),
  );
});
