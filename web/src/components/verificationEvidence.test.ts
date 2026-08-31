import { describe, expect, test } from "vitest";

import type { TimelineItem } from "../state/store";
import { buildVerificationRepairTask } from "./verificationEvidence";

describe("buildVerificationRepairTask", () => {
  test("creates a visible repair request from the failed validation evidence", () => {
    const items: TimelineItem[] = [
      {
        id: "validation",
        kind: "activity",
        turnId: "turn-1",
        activityId: "validation-1",
        activityKind: "validation",
        title: "验证失败",
        summary: "pytest failed",
        status: "failed",
        detail: {
          summary: "pytest failed",
          data: {
            command: "python -m pytest -q",
            exit_code: 1,
            stderr: "AssertionError: expected 2",
          },
        },
      },
    ];

    const task = buildVerificationRepairTask(items, "turn-1");

    expect(task).toContain("请修复以下验证失败");
    expect(task).toContain("python -m pytest -q");
    expect(task).toContain("AssertionError: expected 2");
    expect(task).toContain("修改后重新运行验证");
  });
});
