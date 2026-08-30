import { promises as fs } from "node:fs";
import path from "node:path";

const CREDENTIAL_NAME = /^FORGE_PROVIDER_[A-Z0-9_]+_API_KEY$/;
const ENVIRONMENT_ASSIGNMENT = /^(?:(?:export|set)\s+|\$env:)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$/i;

function normalizedProvider(provider: string): string {
  return provider.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase();
}

export function providerCredentialName(provider: string): string {
  const normalized = normalizedProvider(provider);
  if (!normalized) throw new Error("Provider name must contain a letter or number");
  return `FORGE_PROVIDER_${normalized}_API_KEY`;
}

function unquote(value: string): string {
  const trimmed = value.trim();
  const first = trimmed[0];
  return trimmed.length >= 2 && (first === "\"" || first === "'") && trimmed.at(-1) === first
    ? trimmed.slice(1, -1).trim()
    : trimmed;
}

function normalizeCredentialInput(value: string): string {
  const trimmed = value.trim();
  const assignment = ENVIRONMENT_ASSIGNMENT.exec(trimmed);
  const normalized = unquote(assignment?.[2] ?? trimmed);
  if (/[\r\n]/.test(normalized)) throw new Error("API Key 不能包含换行");
  return normalized;
}

export function resolveProviderCredential(
  provider: string,
  input: string,
  environment: Readonly<Record<string, string | undefined>> = process.env,
): string {
  const normalized = normalizedProvider(provider);
  const providerName = providerCredentialName(provider);
  const aliases =
    normalized === "GEMINI"
      ? [providerName, "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"]
      : [providerName, `${normalized}_API_KEY`, "OPENAI_API_KEY"];
  let credential = normalizeCredentialInput(input);
  if (!credential) {
    credential = aliases
      .map((name) => normalizeCredentialInput(environment[name] ?? ""))
      .find(Boolean) ?? "";
  }
  if (!credential) {
    throw new Error("未找到 API Key；请输入密钥，或先设置对应的环境变量");
  }
  if (normalized === "GEMINI" && !/^AIza[0-9A-Za-z_-]{20,}$/.test(credential)) {
    throw new Error("Gemini API Key 格式无效；请粘贴 AIza… 密钥，不要只填写变量名");
  }
  return credential;
}

export interface EncryptionAdapter {
  isEncryptionAvailable(): boolean;
  isAsyncEncryptionAvailable?(): boolean | Promise<boolean>;
  getSelectedStorageBackend?(): string;
  encryptString?(value: string): Buffer;
  decryptString?(value: Buffer): string;
  encryptStringAsync?(value: string): Promise<Buffer>;
  decryptStringAsync?(value: Buffer): Promise<string | { result: string; shouldReEncrypt: boolean }>;
}

interface CredentialFile {
  version: 1;
  credentials: Record<string, string>;
}

export interface CredentialStoreOptions {
  storePath: string;
  encryption: EncryptionAdapter;
  platform: NodeJS.Platform;
}

export interface CredentialSaveResult {
  persisted: boolean;
  backend: string;
}

export interface StagedCredential {
  result: CredentialSaveResult;
  rollback(): Promise<void>;
}

export class CredentialStore {
  private readonly memory = new Map<string, string>();
  private readonly storePath: string;
  private readonly encryption: EncryptionAdapter;
  private readonly platform: NodeJS.Platform;

  constructor(options: CredentialStoreOptions) {
    this.storePath = options.storePath;
    this.encryption = options.encryption;
    this.platform = options.platform;
  }

  async save(name: string, secret: string): Promise<CredentialSaveResult> {
    return (await this.stage(name, secret)).result;
  }

  async stage(name: string, secret: string): Promise<StagedCredential> {
    this.assertName(name);
    if (!secret) throw new Error("API key must not be empty");
    const backend = this.selectedBackend();
    if (!(await this.canPersist(backend))) {
      const previous = this.memory.get(name);
      this.memory.set(name, secret);
      return {
        result: { persisted: false, backend: "memory" },
        rollback: async () => {
          if (this.memory.get(name) !== secret) return;
          if (previous === undefined) this.memory.delete(name);
          else this.memory.set(name, previous);
        },
      };
    }

    const file = await this.readFile();
    const previous = file.credentials[name];
    const staged = (await this.encrypt(secret)).toString("base64");
    file.credentials[name] = staged;
    await this.writeFile(file);
    this.memory.delete(name);
    return {
      result: { persisted: true, backend },
      rollback: async () => {
        const current = await this.readFile();
        if (current.credentials[name] !== staged) return;
        if (previous === undefined) delete current.credentials[name];
        else current.credentials[name] = previous;
        await this.writeFile(current);
      },
    };
  }

  async environment(): Promise<Record<string, string>> {
    const environment: Record<string, string> = {};
    const backend = this.selectedBackend();
    if (await this.canPersist(backend)) {
      const file = await this.readFile();
      for (const [name, encoded] of Object.entries(file.credentials)) {
        this.assertName(name);
        environment[name] = await this.decrypt(Buffer.from(encoded, "base64"));
      }
    }
    for (const [name, secret] of this.memory) environment[name] = secret;
    return environment;
  }

  async delete(name: string): Promise<void> {
    this.assertName(name);
    this.memory.delete(name);
    const backend = this.selectedBackend();
    if (!(await this.canPersist(backend))) return;
    const file = await this.readFile();
    if (!(name in file.credentials)) return;
    delete file.credentials[name];
    await this.writeFile(file);
  }

  private selectedBackend(): string {
    return this.encryption.getSelectedStorageBackend?.() ?? "os-encryption";
  }

  private async canPersist(backend: string): Promise<boolean> {
    const available = this.encryption.isAsyncEncryptionAvailable
      ? await this.encryption.isAsyncEncryptionAvailable()
      : this.encryption.isEncryptionAvailable();
    return available && !(this.platform === "linux" && backend === "basic_text");
  }

  private assertName(name: string): void {
    if (!CREDENTIAL_NAME.test(name)) throw new Error("Invalid provider credential name");
  }

  private async encrypt(secret: string): Promise<Buffer> {
    if (this.encryption.encryptStringAsync) {
      return Buffer.from(await this.encryption.encryptStringAsync(secret));
    }
    if (this.encryption.encryptString) return this.encryption.encryptString(secret);
    throw new Error("Operating-system encryption is unavailable");
  }

  private async decrypt(value: Buffer): Promise<string> {
    if (this.encryption.decryptStringAsync) {
      const decrypted = await this.encryption.decryptStringAsync(value);
      return typeof decrypted === "string" ? decrypted : decrypted.result;
    }
    if (this.encryption.decryptString) return this.encryption.decryptString(value);
    throw new Error("Operating-system encryption is unavailable");
  }

  private async readFile(): Promise<CredentialFile> {
    try {
      const raw = JSON.parse(await fs.readFile(this.storePath, "utf8")) as unknown;
      if (typeof raw !== "object" || raw === null) throw new Error("invalid credential file");
      const record = raw as Record<string, unknown>;
      if (record.version !== 1 || typeof record.credentials !== "object" || record.credentials === null) {
        throw new Error("invalid credential file");
      }
      const credentials: Record<string, string> = {};
      for (const [name, value] of Object.entries(record.credentials)) {
        if (typeof value !== "string") throw new Error("invalid credential file");
        credentials[name] = value;
      }
      return { version: 1, credentials };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return { version: 1, credentials: {} };
      throw error;
    }
  }

  private async writeFile(file: CredentialFile): Promise<void> {
    await fs.mkdir(path.dirname(this.storePath), { recursive: true });
    const temporary = `${this.storePath}.${process.pid}.tmp`;
    await fs.writeFile(temporary, `${JSON.stringify(file, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
    await fs.rename(temporary, this.storePath);
  }
}
