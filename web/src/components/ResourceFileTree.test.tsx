import { render, screen } from "@testing-library/react";

import { ResourceFileTree } from "./ResourceFileTree";

test("marks nested child groups so directory guide lines can follow tree depth", () => {
  render(
    <ResourceFileTree
      paths={["src/coding_agent/runtime.py", "src/coding_agent/tools/registry.py"]}
      statuses={new Map([["src/coding_agent/runtime.py", "read"]])}
      selectedPath={null}
      onSelect={() => undefined}
    />,
  );

  const groups = screen
    .getAllByRole("group")
    .filter((group) => group.classList.contains("resource-tree-children"));
  expect(groups).toHaveLength(3);
  expect(groups[0]).toHaveClass("resource-tree-children");
  expect(groups[0]).toHaveStyle({ "--tree-guide-depth": "0" });
  expect(groups[1]).toHaveStyle({ "--tree-guide-depth": "1" });
  expect(groups[2]).toHaveStyle({ "--tree-guide-depth": "2" });
});
