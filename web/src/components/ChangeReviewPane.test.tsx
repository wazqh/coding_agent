import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { ChangeReviewPane } from "./ChangeReviewPane";

test("reviews a selected change in an adjacent conversation pane", () => {
  const onClose = vi.fn();
  const onReview = vi.fn();
  render(
    <ChangeReviewPane
      change={{
        id: "change-1",
        path: "src/demo.py",
        kind: "modified",
        additions: 1,
        deletions: 1,
        diff: "--- a/src/demo.py\n+++ b/src/demo.py\n@@ -1 +1 @@\n-old\n+new\n",
      }}
      drawerWidth={438}
      onReview={onReview}
      onClose={onClose}
    />,
  );

  expect(screen.getByRole("dialog", { name: "src/demo.py 变更审查" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "放大审查" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "接受改动" }));
  expect(onReview).toHaveBeenCalledWith("change-1", "accept");
  fireEvent.click(screen.getByRole("button", { name: "关闭变更审查" }));
  expect(onClose).toHaveBeenCalledOnce();
});
