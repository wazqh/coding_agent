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

test("renders command verification evidence as readable vertical sections", () => {
  const view = render(
    <StructuredToolDetail
      activityKind="validation"
      detail={{
        code: "COMMAND_FAILED",
        summary: "command exited with code 1",
        data: {
          command: "python -m pytest leetcode_hot100/tests -q",
          cwd: "leetcode_hot100",
          exit_code: 1,
          stdout: "FAILED test_trapping_rain_water.py::test_example\n1 failed",
          stderr: "",
          verification: true,
          verification_status: "test_failed",
          verification_check: {
            id: "algorithm-tests",
            label: "算法用例",
            kind: "test",
            command: "python -m pytest tests -q",
            cwd: "leetcode_hot100",
            timeout_seconds: 120,
            enabled: true,
          },
        },
      }}
    />,
  );

  expect(screen.getByRole("group", { name: "验证结果详情" })).toBeInTheDocument();
  expect(screen.getByText("测试未通过")).toBeInTheDocument();
  expect(screen.getByText("python -m pytest leetcode_hot100/tests -q")).toBeInTheDocument();
  expect(screen.getByText("leetcode_hot100").closest(".command-result-meta dd")).toBeInTheDocument();
  expect(screen.getByText("算法用例")).toBeInTheDocument();
  expect(screen.getByText("FAILED test_trapping_rain_water.py::test_example", { exact: false })).toBeInTheDocument();
  expect(view.container.querySelector(".structured-fields")).toBeNull();
  expect(view.container.textContent).not.toContain("COMMAND_FAILED");
  expect(view.container.textContent).not.toContain("verification_status");
});
