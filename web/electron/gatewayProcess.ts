import { spawn } from "node:child_process";
import type { Readable } from "node:stream";

import type { GatewayCommand, GatewayReady, GatewayState } from "./types.js";

const HANDSHAKE_PREFIX = "FORGE_DESKTOP_READY ";
const TRUST_REQUIRED_PREFIX = "FORGE_DESKTOP_TRUST_REQUIRED ";
const CAPABILITY_PATTERN = /^[A-Za-z0-9_-]{1,512}$/;

export type ProjectTrustChoice = "once" | "always" | "ignore";

export class GatewayTrustRequiredError extends Error {
  readonly workspace: string;

  constructor(workspace: string) {
    super("Project resources require a desktop trust decision");
    this.name = "GatewayTrustRequiredError";
    this.workspace = workspace;
  }
}

export interface GatewayChild {
  readonly stdout: Readable;
  readonly stderr: Readable;
  exitCode: number | null;
  kill(signal?: NodeJS.Signals): boolean;
  on(event: "exit", listener: (code: number | null, signal: NodeJS.Signals | null) => void): this;
  once(event: "exit", listener: (code: number | null, signal: NodeJS.Signals | null) => void): this;
  once(event: "error", listener: (error: Error) => void): this;
}

export type SpawnGateway = (
  file: string,
  args: string[],
  options: {
    shell: false;
    windowsHide: true;
    stdio: ["ignore", "pipe", "pipe"];
    env: NodeJS.ProcessEnv;
  },
) => GatewayChild;

export interface GatewayStartOptions {
  pythonExecutable: string;
  workspace: string;
  timeoutMs?: number;
  environment?: Record<string, string>;
  trustMode?: ProjectTrustChoice;
}

const defaultSpawnGateway: SpawnGateway = (file, args, options) =>
  spawn(file, args, options) as GatewayChild;

export function buildGatewayCommand(
  pythonExecutable: string,
  workspace: string,
  trustMode?: ProjectTrustChoice,
): GatewayCommand {
  if (!pythonExecutable.trim()) {
    throw new Error("Python executable is required");
  }
  if (!workspace.trim()) {
    throw new Error("Workspace path is required");
  }
  const args = [
    "-m",
    "coding_agent",
    "web",
    "--cwd",
    workspace,
    "--no-open",
    "--desktop-handshake",
  ];
  if (trustMode) args.push("--desktop-trust", trustMode);
  return {
    file: pythonExecutable,
    args,
  };
}

export function parseGatewayTrustRequired(line: string): { workspace: string } {
  if (line.length > 8192 || !line.startsWith(TRUST_REQUIRED_PREFIX)) {
    throw new Error("Invalid desktop trust challenge");
  }
  let value: unknown;
  try {
    value = JSON.parse(line.slice(TRUST_REQUIRED_PREFIX.length));
  } catch {
    throw new Error("Invalid desktop trust challenge JSON");
  }
  if (typeof value !== "object" || value === null) {
    throw new Error("Invalid desktop trust challenge payload");
  }
  const workspace = (value as Record<string, unknown>).workspace;
  if (typeof workspace !== "string" || !workspace.trim() || workspace.length > 4096) {
    throw new Error("Desktop trust challenge workspace is invalid");
  }
  return { workspace };
}

export function parseGatewayHandshake(line: string): GatewayReady {
  if (line.length > 8192 || !line.startsWith(HANDSHAKE_PREFIX)) {
    throw new Error("Invalid desktop gateway handshake");
  }
  let value: unknown;
  try {
    value = JSON.parse(line.slice(HANDSHAKE_PREFIX.length));
  } catch {
    throw new Error("Invalid desktop gateway handshake JSON");
  }
  if (typeof value !== "object" || value === null) {
    throw new Error("Invalid desktop gateway handshake payload");
  }
  const record = value as Record<string, unknown>;
  if (typeof record.origin !== "string" || typeof record.capability !== "string") {
    throw new Error("Invalid desktop gateway handshake fields");
  }
  let origin: URL;
  try {
    origin = new URL(record.origin);
  } catch {
    throw new Error("Desktop gateway origin is not a URL");
  }
  if (
    origin.protocol !== "http:" ||
    origin.hostname !== "127.0.0.1" ||
    !origin.port ||
    origin.origin !== record.origin ||
    origin.username ||
    origin.password
  ) {
    throw new Error("Desktop gateway origin must be an exact loopback HTTP origin");
  }
  if (!CAPABILITY_PATTERN.test(record.capability)) {
    throw new Error("Desktop gateway capability is invalid");
  }
  return { origin: record.origin, capability: record.capability };
}

export class GatewayProcess {
  state: GatewayState = "idle";

  private child: GatewayChild | null = null;
  private readonly spawnGateway: SpawnGateway;

  constructor(spawnGateway: SpawnGateway = defaultSpawnGateway) {
    this.spawnGateway = spawnGateway;
  }

  start(options: GatewayStartOptions): Promise<GatewayReady> {
    if (this.child !== null || this.state === "starting" || this.state === "ready") {
      return Promise.reject(new Error("Desktop gateway is already running"));
    }
    const command = buildGatewayCommand(
      options.pythonExecutable,
      options.workspace,
      options.trustMode,
    );
    this.state = "starting";
    const child = this.spawnGateway(command.file, command.args, {
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ...options.environment },
    });
    this.child = child;
    child.stderr.resume();

    return new Promise<GatewayReady>((resolve, reject) => {
      let buffer = "";
      let settled = false;
      const timeoutMs = options.timeoutMs ?? 20_000;
      const timer = setTimeout(() => {
        fail(new Error(`Desktop gateway startup timed out after ${timeoutMs}ms`));
      }, timeoutMs);

      const fail = (error: Error): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        this.state = "failed";
        if (child.exitCode === null) child.kill();
        reject(error);
      };

      child.stdout.on("data", (chunk: Buffer | string) => {
        if (settled) return;
        buffer += chunk.toString();
        if (buffer.length > 8192) {
          fail(new Error("Desktop gateway handshake exceeded 8192 bytes"));
          return;
        }
        const newline = buffer.indexOf("\n");
        if (newline < 0) return;
        const line = buffer.slice(0, newline).replace(/\r$/, "");
        try {
          if (line.startsWith(TRUST_REQUIRED_PREFIX)) {
            const challenge = parseGatewayTrustRequired(line);
            throw new GatewayTrustRequiredError(challenge.workspace);
          }
          const ready = parseGatewayHandshake(line);
          settled = true;
          clearTimeout(timer);
          this.state = "ready";
          resolve(ready);
        } catch (error) {
          fail(error instanceof Error ? error : new Error("Invalid desktop gateway handshake"));
        }
      });
      child.once("error", fail);
      child.on("exit", (code, signal) => {
        if (!settled) {
          fail(
            new Error(
              `Desktop gateway exited before startup (code ${String(code)}, signal ${String(signal)})`,
            ),
          );
          return;
        }
        if (this.state === "stopping") this.state = "stopped";
        else if (this.state === "ready") this.state = "failed";
        if (this.child === child) this.child = null;
      });
    });
  }

  async stop(timeoutMs = 2000): Promise<void> {
    const child = this.child;
    if (child === null || child.exitCode !== null) {
      this.child = null;
      this.state = "stopped";
      return;
    }
    this.state = "stopping";
    await new Promise<void>((resolve) => {
      let done = false;
      const finish = (): void => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve();
      };
      const timer = setTimeout(finish, timeoutMs);
      child.once("exit", finish);
      child.kill();
    });
    if (this.child === child) this.child = null;
    this.state = "stopped";
  }
}
