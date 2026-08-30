import { render, screen } from "@testing-library/react";

import { WorkspaceHeader } from "./WorkspaceHeader";

test("keeps a compact conversation title beside the project identity", () => {
  render(
    <WorkspaceHeader
      taskTitle="使用 update_plan，规划一下我后续要如何优化这个项目并给出完整的实施说明"
      projectName="coding_agent"
      onToggleRail={() => undefined}
    />,
  );

  expect(
    screen.getByRole("heading", { name: "使用 update_plan，规划一下我后续要如何优化这…" }),
  ).toBeInTheDocument();
  expect(screen.getByText("coding_agent")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "任务检查器" })).not.toBeInTheDocument();
});
