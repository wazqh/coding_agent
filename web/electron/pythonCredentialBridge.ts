import { spawn } from "node:child_process";

export interface CredentialBridgeProcessResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

export type CredentialBridgeRunner = (
  pythonExecutable: string,
  args: readonly string[],
  input: string,
  environment: NodeJS.ProcessEnv,
) => Promise<CredentialBridgeProcessResult>;

const runBridgeProcess: CredentialBridgeRunner = (pythonExecutable, args, input, environment) =>
  new Promise((resolve, reject) => {
    const child = spawn(pythonExecutable, args, {
      env: environment,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      if (stdout.length < 64_000) stdout += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      if (stderr.length < 64_000) stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, stdout, stderr }));
    child.stdin.end(input);
  });

export function credentialNameToReference(name: string): string {
  const matched = /^FORGE_PROVIDER_([A-Z0-9_]+)_API_KEY$/.exec(name);
  if (!matched?.[1]) throw new Error("Invalid provider credential name");
  return `provider:${matched[1].toLowerCase().replaceAll("_", "-")}`;
}

export class PythonCredentialBridge {
  constructor(
    private readonly pythonExecutable: string,
    private readonly environment: NodeJS.ProcessEnv,
    private readonly runner: CredentialBridgeRunner = runBridgeProcess,
  ) {}

  async has(reference: string): Promise<boolean> {
    const result = await this.invoke("has", reference, "");
    return result.present === true;
  }

  async set(reference: string, secret: string): Promise<{ persisted: boolean }> {
    const result = await this.invoke("set", reference, secret);
    return { persisted: result.persisted === true };
  }

  async copy(source: string, target: string): Promise<{ persisted: boolean }> {
    const result = await this.invoke("copy", source, "", target);
    return { persisted: result.persisted === true };
  }

  async delete(reference: string): Promise<void> {
    await this.invoke("delete", reference, "");
  }

  private async invoke(
    action: "has" | "set" | "copy" | "delete",
    reference: string,
    input: string,
    target?: string,
  ): Promise<Record<string, unknown>> {
    const args = ["-m", "coding_agent.credential_bridge", action, reference];
    if (target) args.push(target);
    const result = await this.runner(
      this.pythonExecutable,
      args,
      input,
      this.environment,
    );
    if (result.code !== 0) throw new Error("Operating-system credential storage is unavailable");
    try {
      const payload = JSON.parse(result.stdout) as unknown;
      if (typeof payload !== "object" || payload === null || (payload as { ok?: unknown }).ok !== true) {
        throw new Error("invalid response");
      }
      return payload as Record<string, unknown>;
    } catch {
      throw new Error("Credential service returned an invalid response");
    }
  }
}
