import { act, render, screen } from "@testing-library/react";
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
  expect(screen.getByText("待审变更 1 项")).toBeInTheDocument();
});

test("uses one clear review action for keeping or reverting the displayed diff", async () => {
  const user = userEvent.setup();
  const onReview = vi.fn();
  render(<DiffViewer change={change} onReview={onReview} />);

  await user.click(screen.getByRole("button", { name: "并排对比" }));
  expect(screen.getByRole("table", { name: "并排 Diff" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "接受改动" }));
  expect(onReview).toHaveBeenCalledWith("change-1", "accept");
  await user.click(screen.getByRole("button", { name: "撤销改动" }));
  expect(onReview).toHaveBeenCalledWith("change-1", "discard");
  expect(screen.queryByRole("button", { name: /放弃|撤销此变更|确认撤销/ })).not.toBeInTheDocument();
});

test("labels batch review with the same keep and revert vocabulary", () => {
  render(
    <ChangesSummary
      changes={[change]}
      onSelect={() => undefined}
      onReviewAll={() => undefined}
    />,
  );

  expect(screen.getByRole("button", { name: "接受全部" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "全部撤销" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "放弃全部" })).not.toBeInTheDocument();
});

test("removes accepted changes from the review queue and briefly confirms the action", () => {
  vi.useFakeTimers();
  const accepted = { ...change, id: "accepted", path: "src/accepted.py", reviewStatus: "accepted" as const };
  const pending = { ...change, id: "pending", path: "src/pending.py", reviewStatus: "pending" as const };

  const view = render(
    <ChangesSummary
      changes={[{ ...accepted, reviewStatus: "pending" as const }, pending]}
      onSelect={() => undefined}
      onReviewAll={() => undefined}
    />,
  );

  view.rerender(
    <ChangesSummary
      changes={[accepted, pending]}
      onSelect={() => undefined}
      onReviewAll={() => undefined}
    />,
  );

  expect(screen.queryByRole("button", { name: /src\/accepted\.py/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /src\/pending\.py/ })).toBeInTheDocument();
  expect(screen.getByRole("status", { name: "已接受 1 项变更" })).toBeInTheDocument();
  expect(screen.getByText("待审变更 1 项")).toBeInTheDocument();

  act(() => vi.advanceTimersByTime(1_800));
  expect(screen.queryByRole("status", { name: "已接受 1 项变更" })).not.toBeInTheDocument();
  vi.useRealTimers();
});

test("does not replay an accepted confirmation when persisted review data loads", () => {
  const accepted = { ...change, reviewStatus: "accepted" as const };
  const { rerender } = render(
    <ChangesSummary changes={[]} onSelect={() => undefined} />,
  );

  rerender(<ChangesSummary changes={[accepted]} onSelect={() => undefined} />);

  expect(screen.queryByRole("status", { name: /已接受/ })).not.toBeInTheDocument();
});
