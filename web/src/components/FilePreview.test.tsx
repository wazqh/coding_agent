import { render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { FilePreview } from "./FilePreview";

vi.mock("./syntaxHighlighter", () => ({
  highlightCode: vi.fn(async () => [[
    { content: ".card", color: "#0550ae" },
    { content: " { color: red; }", color: "#24292f" },
  ]]),
}));

test("syntax-highlights supported workspace previews while preserving line numbers", async () => {
  render(<FilePreview file={{ path: "theme.css", language: "css", size: 21, text: ".card { color: red; }" }} />);

  expect(screen.getByText("1")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText(".card")).toHaveStyle({ color: "#0550ae" }));
});
