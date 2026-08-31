import { render, screen, within } from "@testing-library/react";

import { CommandGuide } from "./CommandGuide";

test("keeps wrapped command descriptions attached to one semantic row", () => {
  render(
    <CommandGuide
      commands={[
        {
          kind: "command",
          label: "/help",
          insert_text: "/help",
          description: "查看命令说明或某个命令的详细用法。",
          replace_start: 0,
          replace_end: 1,
        },
        {
          kind: "command",
          label: "/permissions",
          insert_text: "/permissions",
          description: "查看或切换工具审批策略，并明确说明设置影响的范围。",
          replace_start: 0,
          replace_end: 1,
        },
      ]}
      onClose={() => undefined}
      onChoose={() => undefined}
    />,
  );

  const list = screen.getByRole("list", { name: "可用命令" });
  const rows = within(list).getAllByRole("listitem");
  expect(rows).toHaveLength(2);
  expect(rows[1]).toHaveTextContent("/permissions");
  expect(rows[1]).toHaveTextContent("查看或切换工具审批策略");
});
