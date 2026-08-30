import path from "node:path";

import { describe, expect, test } from "vitest";

import { resolveConfiguredWorkspace } from "./workspaceConfig.js";

describe("resolveConfiguredWorkspace", () => {
  test("prefers --cwd over the environment and process directory", () => {
    expect(
      resolveConfiguredWorkspace(
        ["electron", ".", "--cwd", "D:\\projects\\chosen"],
        { FORGE_WORKSPACE: "D:\\projects\\environment" },
        "D:\\projects\\fallback",
      ),
    ).toBe(path.resolve("D:\\projects\\chosen"));
  });

  test("uses FORGE_WORKSPACE when npm does not forward --cwd", () => {
    expect(
      resolveConfiguredWorkspace(
        ["electron", "."],
        { FORGE_WORKSPACE: "D:\\projects\\forge" },
        "D:\\codes\\coding_agent\\web",
      ),
    ).toBe(path.resolve("D:\\projects\\forge"));
  });

  test("falls back to the process directory for blank configuration", () => {
    expect(
      resolveConfiguredWorkspace(
        ["electron", "."],
        { FORGE_WORKSPACE: "   " },
        "D:\\projects\\fallback",
      ),
    ).toBe(path.resolve("D:\\projects\\fallback"));
  });
});
