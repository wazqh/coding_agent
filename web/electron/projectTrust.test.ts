import { describe, expect, test } from "vitest";

import { projectTrustChoice } from "./projectTrust.js";

describe("projectTrustChoice", () => {
  test.each([
    [0, "ignore"],
    [1, "once"],
    [2, "always"],
    [-1, "ignore"],
  ] as const)("maps desktop dialog response %s to %s", (response, expected) => {
    expect(projectTrustChoice(response)).toBe(expected);
  });
});
