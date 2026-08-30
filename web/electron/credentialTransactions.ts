import { randomUUID } from "node:crypto";

import { CredentialStore, type CredentialSaveResult } from "./credentialStore.js";
import { credentialNameToReference } from "./pythonCredentialBridge.js";

export interface CredentialTransactionResult extends CredentialSaveResult {
  transactionId: string;
}

export interface SharedCredentialWriter {
  set(reference: string, secret: string): Promise<{ persisted: boolean }>;
}

interface PendingCredential {
  name: string;
  secret: string;
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
    this.pending.set(transactionId, { name, secret, rollback: staged.rollback });
    return { ...staged.result, transactionId };
  }

  async commit(transactionId: string): Promise<boolean> {
    const pending = this.pending.get(transactionId);
    if (!pending) return false;
    if (this.shared) {
      const saved = await this.shared.set(credentialNameToReference(pending.name), pending.secret);
      if (!saved.persisted) throw new Error("Credential was not persisted securely");
      await this.store.delete(pending.name);
    }
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
