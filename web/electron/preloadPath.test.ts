import path from "node:path";

import { describe, expect, test } from "vitest";

import { resolvePreloadPath } from "./preloadPath.js";

describe("resolvePreloadPath", () => {
  test("uses a CommonJS preload compatible with Electron's sandbox", () => {
    expect(resolvePreloadPath("D:\\app\\dist-electron")).toBe(
      path.join("D:\\app\\dist-electron", "preload.cjs"),
    );
  });
});
