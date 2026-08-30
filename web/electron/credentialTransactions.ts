import { randomUUID } from "node:crypto";

import { CredentialStore, type CredentialSaveResult } from "./credentialStore.js";

export interface CredentialTransactionResult extends CredentialSaveResult {
  transactionId: string;
}

export class CredentialTransactionManager {
  private readonly pending = new Map<string, () => Promise<void>>();

  constructor(
    private readonly store: CredentialStore,
    private readonly createId: () => string = randomUUID,
  ) {}

  async stage(name: string, secret: string): Promise<CredentialTransactionResult> {
    const staged = await this.store.stage(name, secret);
    const transactionId = this.createId();
    if (this.pending.has(transactionId)) {
      await staged.rollback();
      throw new Error("Credential transaction ID collision");
    }
    this.pending.set(transactionId, staged.rollback);
    return { ...staged.result, transactionId };
  }

  commit(transactionId: string): boolean {
    return this.pending.delete(transactionId);
  }

  async rollback(transactionId: string): Promise<boolean> {
    const rollback = this.pending.get(transactionId);
    if (!rollback) return false;
    this.pending.delete(transactionId);
    await rollback();
    return true;
  }
}
