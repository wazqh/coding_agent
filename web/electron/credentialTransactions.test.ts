import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, expect, test } from "vitest";

import { CredentialStore, type EncryptionAdapter } from "./credentialStore";
import { CredentialTransactionManager } from "./credentialTransactions";

const tempDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(tempDirectories.splice(0).map((directory) => fs.rm(directory, { recursive: true })));
});

function encryption(): EncryptionAdapter {
  return {
    isEncryptionAvailable: () => true,
    getSelectedStorageBackend: () => "dpapi",
    encryptString: (value) => Buffer.from(`encrypted:${value}`, "utf8"),
    decryptString: (value) => value.toString("utf8").replace(/^encrypted:/, ""),
  };
}

async function manager(): Promise<{
  store: CredentialStore;
  transactions: CredentialTransactionManager;
}> {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "forge-credential-transactions-"));
  tempDirectories.push(directory);
  const store = new CredentialStore({
    storePath: path.join(directory, "credentials.json"),
    encryption: encryption(),
    platform: "win32",
  });
  const shared = {
    has: async () => false,
    set: async (reference: string, secret: string) => {
      expect(reference).toBe("provider:demo");
      expect(secret).toBe("new-secret");
      return { persisted: true };
    },
    copy: async () => ({ persisted: true }),
    delete: async () => undefined,
  };
  return {
    store,
    transactions: new CredentialTransactionManager(store, () => "transaction-1", shared),
  };
}

test("rollback restores the previous credential without exposing it through the transaction result", async () => {
  const { store, transactions } = await manager();
  await store.save("FORGE_PROVIDER_DEMO_API_KEY", "old-secret");

  const result = await transactions.stage("FORGE_PROVIDER_DEMO_API_KEY", "new-secret");
  expect(result).toEqual({ persisted: true, backend: "dpapi", transactionId: "transaction-1" });

  await expect(transactions.rollback(result.transactionId)).resolves.toBe(true);
  await expect(store.environment()).resolves.toEqual({ FORGE_PROVIDER_DEMO_API_KEY: "old-secret" });
});

test("committing writes the shared credential and removes the legacy desktop copy", async () => {
  const { store, transactions } = await manager();
  const result = await transactions.stage("FORGE_PROVIDER_DEMO_API_KEY", "new-secret");

  await expect(transactions.commit(result.transactionId)).resolves.toBe(true);
  await expect(transactions.rollback(result.transactionId)).resolves.toBe(false);
  await expect(store.environment()).resolves.toEqual({});
});

test("copies a shared credential transactionally without exposing its secret", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "forge-credential-copy-"));
  tempDirectories.push(directory);
  const store = new CredentialStore({
    storePath: path.join(directory, "credentials.json"),
    encryption: encryption(),
    platform: "win32",
  });
  const copied = new Map<string, string>([["provider:source", "top-secret"]]);
  const shared = {
    has: async (reference: string) => copied.has(reference),
    set: async () => ({ persisted: true }),
    copy: async (source: string, target: string) => {
      const secret = copied.get(source);
      if (!secret) throw new Error("missing source");
      copied.set(target, secret);
      return { persisted: true };
    },
    delete: async (reference: string) => {
      copied.delete(reference);
    },
  };
  const transactions = new CredentialTransactionManager(store, () => "copy-transaction", shared);

  const result = await transactions.stageCopy(
    "FORGE_PROVIDER_SOURCE_API_KEY",
    "FORGE_PROVIDER_TARGET_API_KEY",
  );

  expect(result).toEqual({
    persisted: true,
    backend: "os-credential-copy",
    transactionId: "copy-transaction",
  });
  expect(JSON.stringify(result)).not.toContain("top-secret");
  expect(copied.get("provider:target")).toBe("top-secret");

  await expect(transactions.rollback(result.transactionId)).resolves.toBe(true);
  expect(copied.has("provider:target")).toBe(false);
  expect(copied.get("provider:source")).toBe("top-secret");
});
