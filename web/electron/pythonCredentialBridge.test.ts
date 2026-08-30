import { expect, test, vi } from "vitest";

import {
  PythonCredentialBridge,
  credentialNameToReference,
  type CredentialBridgeRunner,
} from "./pythonCredentialBridge.js";

test("maps provider environment names to shared credential references", () => {
  expect(credentialNameToReference("FORGE_PROVIDER_OPEN_ROUTER_API_KEY")).toBe(
    "provider:open-router",
  );
});

test("passes a secret through stdin and never through process arguments", async () => {
  const runner = vi.fn<CredentialBridgeRunner>(async (_python, args, input) => {
    expect(args).toEqual([
      "-m",
      "coding_agent.credential_bridge",
      "set",
      "provider:gemini",
    ]);
    expect(args.join(" ")).not.toContain("top-secret");
    expect(input).toBe("top-secret");
    return { code: 0, stdout: '{"ok":true,"persisted":true}', stderr: "" };
  });
  const bridge = new PythonCredentialBridge("python", {}, runner);

  await expect(bridge.set("provider:gemini", "top-secret")).resolves.toEqual({
    persisted: true,
  });
  expect(runner).toHaveBeenCalledOnce();
});

test("checks presence without retrieving a secret", async () => {
  const runner = vi.fn<CredentialBridgeRunner>(async () => ({
    code: 0,
    stdout: '{"ok":true,"present":true,"persistent":true}',
    stderr: "",
  }));
  const bridge = new PythonCredentialBridge("python", {}, runner);

  await expect(bridge.has("provider:gemini")).resolves.toBe(true);
});
