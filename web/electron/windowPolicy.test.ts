import { describe, expect, it } from "vitest";

import { isAllowedNavigation, isExternalHttpUrl } from "./windowPolicy";

describe("desktop window policy", () => {
  it("allows only navigation within the exact gateway origin", () => {
    const origin = "http://127.0.0.1:43210";

    expect(isAllowedNavigation(`${origin}/chat`, origin)).toBe(true);
    expect(isAllowedNavigation("http://127.0.0.1:43211/chat", origin)).toBe(false);
    expect(isAllowedNavigation("https://example.com", origin)).toBe(false);
    expect(isAllowedNavigation("not a url", origin)).toBe(false);
  });

  it("recognizes only http and https links as external candidates", () => {
    expect(isExternalHttpUrl("https://openai.com")).toBe(true);
    expect(isExternalHttpUrl("http://example.com/path")).toBe(true);
    expect(isExternalHttpUrl("file:///C:/Windows/win.ini")).toBe(false);
    expect(isExternalHttpUrl("javascript:alert(1)")).toBe(false);
  });
});
