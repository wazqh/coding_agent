import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

import { ChangesSummary } from "./ChangesSummary";
import { DiffViewer } from "./DiffViewer";

const change = {
  id: "change-1",
  path: "src/demo.py",
  kind: "modified" as const,
  additions: 1,
  deletions: 1,
  diff:
    "--- a/src/demo.py\n+++ b/src/demo.py\n@@ -1 +1 @@\n-old value\n+new value with a very long line that must scroll instead of widening the page\n",
};

test("renders additions and deletions in a horizontally bounded diff", () => {
  render(<DiffViewer change={change} />);

  expect(screen.getByText("+1")).toBeInTheDocument();
  expect(screen.getByText("−1")).toBeInTheDocument();
  expect(screen.getByText(/new value with a very long line/)).toBeInTheDocument();
  expect(screen.getByTestId("diff-scroll")).toHaveClass("diff-scroll");
});

test("switches the same preview frame between diff and a light file view", async () => {
  const user = userEvent.setup();
  const onPreview = vi.fn();
  const view = render(
    <DiffViewer change={change} onPreview={onPreview} previewOpen={false} />,
  );

  expect(screen.getByText(/new value with a very long line/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "查看文件" }));
  expect(onPreview).toHaveBeenCalledWith("src/demo.py");

  view.rerender(
    <DiffViewer
      change={change}
      onPreview={onPreview}
      previewOpen
      filePreview={{
        path: "src/demo.py",
        language: "python",
        size: 10,
        text: "full file\n",
      }}
    />,
  );

  expect(screen.getByRole("button", { name: "查看 Diff" })).toBeInTheDocument();
  expect(screen.getByText("full file")).toBeInTheDocument();
  expect(screen.queryByText(/new value with a very long line/)).not.toBeInTheDocument();
  expect(screen.getByTestId("file-content-scroll")).toHaveClass("diff-scroll");
});

test("summarizes changes and provides a deliberate empty state", () => {
  const view = render(<ChangesSummary changes={[]} onSelect={() => undefined} />);
  expect(screen.getByText("本次运行还没有 Agent 变更")).toBeInTheDocument();

  view.rerender(<ChangesSummary changes={[change]} onSelect={() => undefined} />);
  expect(screen.getByRole("button", { name: /src\/demo.py/ })).toBeInTheDocument();
  expect(screen.getByText("Agent 修改 1 处")).toBeInTheDocument();
});

test("offers undo for the exact displayed diff with an explicit confirmation", async () => {
  const user = userEvent.setup();
  const onUndo = vi.fn();
  render(<DiffViewer change={change} onUndo={onUndo} />);

  await user.click(screen.getByRole("button", { name: "撤销此变更" }));
  expect(onUndo).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "确认撤销" }));

  expect(onUndo).toHaveBeenCalledWith("change-1");
});

test("switches review layout and exposes explicit accept and discard actions", async () => {
  const user = userEvent.setup();
  const onReview = vi.fn();
  render(<DiffViewer change={change} onReview={onReview} />);

  await user.click(screen.getByRole("button", { name: "并排对比" }));
  expect(screen.getByRole("table", { name: "并排 Diff" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "接受此变更" }));
  expect(onReview).toHaveBeenCalledWith("change-1", "accept");
  await user.click(screen.getByRole("button", { name: "放弃此变更" }));
  expect(onReview).toHaveBeenCalledWith("change-1", "discard");
});
