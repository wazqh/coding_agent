import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ActivityDetailPane } from "./ActivityDetailPane";

test("opens command evidence in a conversation-side review pane", async () => {
  const user = userEvent.setup();
  const onClose = vi.fn();

  render(
    <ActivityDetailPane
      drawerWidth={438}
      item={{
        id: "activity:verify-1",
        kind: "activity",
        activityId: "verify-1",
        activityKind: "validation",
        title: "验证失败",
        summary: "command exited with code 1",
        status: "failed",
        detail: {
          code: "COMMAND_FAILED",
          data: {
            command: "python -m pytest tests -q",
            cwd: "algorithm_practice",
            exit_code: 1,
            stdout: "1 failed",
            verification: true,
            verification_status: "test_failed",
          },
        },
      }}
      onClose={onClose}
    />,
  );

  expect(screen.getByRole("dialog", { name: "验证执行详情" })).toBeInTheDocument();
  expect(screen.getByText("python -m pytest tests -q")).toBeInTheDocument();
  expect(screen.getByText("algorithm_practice")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "关闭执行详情" }));
  expect(onClose).toHaveBeenCalledOnce();
});
