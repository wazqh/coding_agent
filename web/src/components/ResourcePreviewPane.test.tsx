import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { ResourcePreviewPane } from "./ResourcePreviewPane";

test("opens a separate adjacent read-only file preview and can close it", () => {
  const onClose = vi.fn();
  render(
    <ResourcePreviewPane
      path="src/demo.py"
      drawerWidth={438}
      file={{ path: "src/demo.py", language: "python", size: 10, text: "answer = 42" }}
      onClose={onClose}
    />,
  );

  const pane = screen.getByRole("dialog", { name: "src/demo.py 文件预览" });
  expect(pane).toHaveStyle({ "--resource-drawer-width": "438px" });
  expect(screen.getByText("answer = 42")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "关闭文件预览" }));
  expect(onClose).toHaveBeenCalledOnce();
});

test("shows immediate loading feedback while a newly selected file is fetched", () => {
  render(
    <ResourcePreviewPane path="README.md" drawerWidth={500} file={null} onClose={vi.fn()} />,
  );

  expect(screen.getByRole("status")).toHaveTextContent("正在读取 README.md");
});

test("keeps the preview inside the conversation area instead of covering the project rail", async () => {
  const conversation = document.createElement("section");
  conversation.className = "conversation";
  vi.spyOn(conversation, "getBoundingClientRect").mockReturnValue({
    left: 248,
    width: 900,
    right: 1148,
    top: 62,
    bottom: 700,
    height: 638,
    x: 248,
    y: 62,
    toJSON: () => ({}),
  });
  document.body.append(conversation);

  render(<ResourcePreviewPane path="README.md" drawerWidth={438} file={null} onClose={vi.fn()} />);

  await waitFor(() => {
    expect(screen.getByRole("dialog")).toHaveStyle({
      "--resource-content-left": "260px",
      "--resource-content-top": "74px",
      "--resource-content-bottom": `${window.innerHeight - 700 + 12}px`,
    });
  });
  conversation.remove();
});
