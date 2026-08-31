import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { SkillCreator } from "./SkillCreator";

test("turns a natural-language requirement into an editable reviewed draft", () => {
  const onDraft = vi.fn(() => true);
  render(<SkillCreator busy={false} draft={null} items={[]} onDraft={onDraft} onCreate={vi.fn()} />);

  fireEvent.click(screen.getByRole("button", { name: "新建 Skill" }));
  fireEvent.change(screen.getByLabelText("Skill 需求"), {
    target: { value: "审查所有工作区边界并给出风险摘要" },
  });
  fireEvent.click(screen.getByRole("button", { name: "代码审查" }));
  fireEvent.click(screen.getByRole("button", { name: "生成可编辑草稿" }));

  expect(onDraft).toHaveBeenCalledWith(
    "审查所有工作区边界并给出风险摘要",
    "review",
  );
  expect(screen.getByRole("status")).toHaveTextContent("正在生成草稿");
});

test("previews and explicitly creates a project or personal skill", () => {
  const onCreate = vi.fn(() => true);
  render(
    <SkillCreator
      busy={false}
      items={[]}
      draft={{
        name: "boundary-review",
        description: "Review workspace boundaries.",
        instructions: "# Workflow\n\nReview the change.",
        generated_by: "model",
      }}
      onDraft={vi.fn()}
      onCreate={onCreate}
    />,
  );

  expect(screen.getByDisplayValue("boundary-review")).toBeInTheDocument();
  expect(screen.getByText("模型生成，可在创建前完整修改")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "当前项目" }));
  fireEvent.click(screen.getByRole("button", { name: "预览 SKILL.md" }));
  expect(screen.getByText(/name: boundary-review/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "创建 Skill" }));

  expect(onCreate).toHaveBeenCalledWith({
    scope: "repo",
    name: "boundary-review",
    description: "Review workspace boundaries.",
    instructions: "# Workflow\n\nReview the change.",
  });
});

test("shows completion feedback when the created skill appears in the catalog", () => {
  const { rerender } = render(
    <SkillCreator
      busy={false}
      items={[]}
      draft={{
        name: "boundary-review",
        description: "Review workspace boundaries.",
        instructions: "# Workflow\n\nReview the change.",
        generated_by: "template",
      }}
      onDraft={vi.fn()}
      onCreate={() => true}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "创建 Skill" }));

  rerender(
    <SkillCreator
      busy={false}
      items={[{ name: "boundary-review" }]}
      draft={null}
      onDraft={vi.fn()}
      onCreate={() => true}
    />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("已创建 $boundary-review");
});
