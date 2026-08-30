import { expect, test, vi } from "vitest";

import { migrateLegacyCredentials } from "./credentialMigration.js";

test("migrates legacy desktop secrets and leaves no child-process environment copy", async () => {
  const remove = vi.fn(async () => undefined);
  const set = vi.fn(async () => ({ persisted: true }));

  const fallback = await migrateLegacyCredentials(
    { FORGE_PROVIDER_GEMINI_API_KEY: "old-secret" },
    { set },
    remove,
  );

  expect(set).toHaveBeenCalledWith("provider:gemini", "old-secret");
  expect(remove).toHaveBeenCalledWith("FORGE_PROVIDER_GEMINI_API_KEY");
  expect(fallback).toEqual({});
});

test("retains process-only fallback when secure migration is unavailable", async () => {
  const remove = vi.fn(async () => undefined);
  const fallback = await migrateLegacyCredentials(
    { FORGE_PROVIDER_GEMINI_API_KEY: "old-secret" },
    { set: async () => { throw new Error("unavailable"); } },
    remove,
  );

  expect(remove).not.toHaveBeenCalled();
  expect(fallback).toEqual({ FORGE_PROVIDER_GEMINI_API_KEY: "old-secret" });
});
