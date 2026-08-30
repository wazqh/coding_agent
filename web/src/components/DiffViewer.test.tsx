import { render, screen } from "@testing-library/react";

import { ChangesSummary } from "./ChangesSummary";
import { DiffViewer } from "./DiffViewer";

const change = {
  id: "change-1",
  path: "src/demo.py",
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

test("summarizes changes and provides a deliberate empty state", () => {
  const view = render(<ChangesSummary changes={[]} onSelect={() => undefined} />);
  expect(screen.getByText("暂时没有文件变更")).toBeInTheDocument();

  view.rerender(<ChangesSummary changes={[change]} onSelect={() => undefined} />);
  expect(screen.getByRole("button", { name: /src\/demo.py/ })).toBeInTheDocument();
  expect(screen.getByText("已记录 1 次改动")).toBeInTheDocument();
});
