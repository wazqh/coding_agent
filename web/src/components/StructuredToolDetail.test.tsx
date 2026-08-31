import { render, screen } from "@testing-library/react";

import { StructuredToolDetail } from "./StructuredToolDetail";

test("renders file changes as a semantic diff and omits implementation-only metadata", () => {
  render(
    <StructuredToolDetail
      detail={{
        code: "OK",
        data: {
          path: "test/README.md",
          sha256: "private-implementation-hash",
          diff: "--- a/test/README.md\n+++ b/test/README.md\n@@ -1 +1 @@\n-old\n+new\n",
          change_id: "internal-change-id",
          change_kind: "modified",
          reversible: true,
        },
      }}
    />,
  );

  expect(screen.getByTestId("diff-scroll")).toBeInTheDocument();
  expect(screen.getByText("test/README.md")).toBeInTheDocument();
  expect(screen.queryByText("private-implementation-hash")).not.toBeInTheDocument();
  expect(screen.queryByText("internal-change-id")).not.toBeInTheDocument();
});
