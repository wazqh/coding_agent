import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  CredentialStore,
  resolveProviderCredential,
  type EncryptionAdapter,
} from "./credentialStore";

const tempDirectories: string[] = [];

async function temporaryPath(): Promise<string> {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "forge-credentials-"));
  tempDirectories.push(directory);
  return path.join(directory, "credentials.json");
}

afterEach(async () => {
  await Promise.all(tempDirectories.splice(0).map((directory) => fs.rm(directory, { recursive: true })));
});

function secureAdapter(backend = "dpapi"): EncryptionAdapter {
  return {
    isEncryptionAvailable: () => true,
    isAsyncEncryptionAvailable: () => true,
    getSelectedStorageBackend: () => backend,
    encryptString: (value) => Buffer.from(`encrypted:${value}`, "utf8"),
    decryptString: (value) => value.toString("utf8").replace(/^encrypted:/, ""),
  };
}

describe("credential store", () => {
  it("uses the provider environment when the desktop form leaves the key blank", () => {
    expect(
      resolveProviderCredential("gemini", "", {
        GEMINI_API_KEY: "AIza-valid-environment-key-123456789",
      }),
    ).toBe("AIza-valid-environment-key-123456789");
  });

  it("normalizes a pasted PowerShell environment assignment", () => {
    expect(
      resolveProviderCredential(
        "gemini",
        "$env:GEMINI_API_KEY = 'AIza-valid-pasted-key-123456789012'",
        {},
      ),
    ).toBe("AIza-valid-pasted-key-123456789012");
  });

  it("rejects a malformed Gemini key before restarting the runtime", () => {
    expect(() => resolveProviderCredential("gemini", "GEMINI_API_KEY", {})).toThrow(
      "Gemini API Key",
    );
  });

  it("persists only encrypted bytes and restores them as child-process environment", async () => {
    const storePath = await temporaryPath();
    const store = new CredentialStore({ storePath, encryption: secureAdapter(), platform: "win32" });

    await expect(store.save("FORGE_PROVIDER_DEMO_API_KEY", "top-secret")).resolves.toEqual({
      persisted: true,
      backend: "dpapi",
    });

    const disk = await fs.readFile(storePath, "utf8");
    expect(disk).not.toContain("top-secret");
    await expect(store.environment()).resolves.toEqual({
      FORGE_PROVIDER_DEMO_API_KEY: "top-secret",
    });
  });

  it("falls back to memory and writes no file for Linux basic_text", async () => {
    const storePath = await temporaryPath();
    const store = new CredentialStore({
      storePath,
      encryption: secureAdapter("basic_text"),
      platform: "linux",
    });

    await expect(store.save("FORGE_PROVIDER_DEMO_API_KEY", "top-secret")).resolves.toEqual({
      persisted: false,
      backend: "memory",
    });
    await expect(fs.stat(storePath)).rejects.toThrow();
    await expect(store.environment()).resolves.toEqual({
      FORGE_PROVIDER_DEMO_API_KEY: "top-secret",
    });
  });

  it("rejects arbitrary environment names", async () => {
    const store = new CredentialStore({
      storePath: await temporaryPath(),
      encryption: secureAdapter(),
      platform: "win32",
    });

    await expect(store.save("PATH", "bad")).rejects.toThrow("credential name");
  });

  it("rolls a staged persistent credential back to the previous secret", async () => {
    const store = new CredentialStore({
      storePath: await temporaryPath(),
      encryption: secureAdapter(),
      platform: "win32",
    });
    await store.save("FORGE_PROVIDER_DEMO_API_KEY", "old-secret");

    const staged = await store.stage("FORGE_PROVIDER_DEMO_API_KEY", "new-secret");
    expect(await store.environment()).toEqual({ FORGE_PROVIDER_DEMO_API_KEY: "new-secret" });

    await staged.rollback();

    await expect(store.environment()).resolves.toEqual({
      FORGE_PROVIDER_DEMO_API_KEY: "old-secret",
    });
  });

  it("removes a first-time in-memory credential when its stage is rolled back", async () => {
    const store = new CredentialStore({
      storePath: await temporaryPath(),
      encryption: secureAdapter("basic_text"),
      platform: "linux",
    });

    const staged = await store.stage("FORGE_PROVIDER_DEMO_API_KEY", "new-secret");
    await staged.rollback();

    await expect(store.environment()).resolves.toEqual({});
  });
});
