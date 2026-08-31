import { randomUUID } from "node:crypto";

import { CredentialStore, type CredentialSaveResult } from "./credentialStore.js";
import { credentialNameToReference } from "./pythonCredentialBridge.js";

export interface CredentialTransactionResult extends CredentialSaveResult {
  transactionId: string;
}

export interface SharedCredentialWriter {
  has(reference: string): Promise<boolean>;
  set(reference: string, secret: string): Promise<{ persisted: boolean }>;
  copy(source: string, target: string): Promise<{ persisted: boolean }>;
  delete(reference: string): Promise<void>;
}

interface PendingCredential {
  commit: () => Promise<void>;
  rollback: () => Promise<void>;
}

export class CredentialTransactionManager {
  private readonly pending = new Map<string, PendingCredential>();

  constructor(
    private readonly store: CredentialStore,
    private readonly createId: () => string = randomUUID,
    private readonly shared?: SharedCredentialWriter,
  ) {}

  async stage(name: string, secret: string): Promise<CredentialTransactionResult> {
    const staged = await this.store.stage(name, secret);
    const transactionId = this.createId();
    if (this.pending.has(transactionId)) {
      await staged.rollback();
      throw new Error("Credential transaction ID collision");
    }
    this.pending.set(transactionId, {
      commit: async () => {
        if (!this.shared) return;
        const saved = await this.shared.set(credentialNameToReference(name), secret);
        if (!saved.persisted) throw new Error("Credential was not persisted securely");
        await this.store.delete(name);
      },
      rollback: staged.rollback,
    });
    return { ...staged.result, transactionId };
  }

  async stageCopy(sourceName: string, targetName: string): Promise<CredentialTransactionResult> {
    if (!this.shared) throw new Error("Operating-system credential storage is unavailable");
    const source = credentialNameToReference(sourceName);
    const target = credentialNameToReference(targetName);
    if (source === target) throw new Error("Source and destination providers must differ");
    if (!(await this.shared.has(source))) throw new Error("Source provider credential was not found");
    if (await this.shared.has(target)) throw new Error("Destination provider credential already exists");
    const copied = await this.shared.copy(source, target);
    if (!copied.persisted) throw new Error("Credential was not persisted securely");

    const transactionId = this.createId();
    if (this.pending.has(transactionId)) {
      await this.shared.delete(target);
      throw new Error("Credential transaction ID collision");
    }
    this.pending.set(transactionId, {
      commit: async () => undefined,
      rollback: async () => this.shared?.delete(target),
    });
    return {
      persisted: true,
      backend: "os-credential-copy",
      transactionId,
    };
  }

  async commit(transactionId: string): Promise<boolean> {
    const pending = this.pending.get(transactionId);
    if (!pending) return false;
    await pending.commit();
    this.pending.delete(transactionId);
    return true;
  }

  async rollback(transactionId: string): Promise<boolean> {
    const pending = this.pending.get(transactionId);
    if (!pending) return false;
    this.pending.delete(transactionId);
    await pending.rollback();
    return true;
  }
}
