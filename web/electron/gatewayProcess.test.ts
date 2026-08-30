import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";

import { describe, expect, it } from "vitest";

import {
  GatewayProcess,
  buildGatewayCommand,
  parseGatewayHandshake,
  parseGatewayTrustRequired,
  type GatewayChild,
  type SpawnGateway,
} from "./gatewayProcess";

class FakeChild extends EventEmitter implements GatewayChild {
  readonly stdout = new PassThrough();
  readonly stderr = new PassThrough();
  exitCode: number | null = null;
  killed = false;

  kill(): boolean {
    this.killed = true;
    this.exitCode = 0;
    this.emit("exit", 0, null);
    return true;
  }
}

describe("gateway process contract", () => {
  it("builds a shell-free Python command for one explicit workspace", () => {
    expect(buildGatewayCommand("python", "D:\\repo")).toEqual({
      file: "python",
      args: [
        "-m",
        "coding_agent",
        "web",
        "--cwd",
        "D:\\repo",
        "--no-open",
        "--desktop-handshake",
      ],
    });
    expect(buildGatewayCommand("python", "D:\\repo", "always").args).toEqual([
      "-m",
      "coding_agent",
      "web",
      "--cwd",
      "D:\\repo",
      "--no-open",
      "--desktop-handshake",
      "--desktop-trust",
      "always",
    ]);
  });

  it("parses a bounded desktop trust challenge", () => {
    expect(
      parseGatewayTrustRequired(
        'FORGE_DESKTOP_TRUST_REQUIRED {"workspace":"D:\\\\repo"}',
      ),
    ).toEqual({ workspace: "D:\\repo" });
    expect(() => parseGatewayTrustRequired("FORGE_DESKTOP_TRUST_REQUIRED {}"))
      .toThrow("workspace");
  });

  it("parses only a bounded loopback startup handshake", () => {
    expect(
      parseGatewayHandshake(
        'FORGE_DESKTOP_READY {"origin":"http://127.0.0.1:43210","capability":"abc_123-XYZ"}',
      ),
    ).toEqual({ origin: "http://127.0.0.1:43210", capability: "abc_123-XYZ" });

    expect(() =>
      parseGatewayHandshake(
        'FORGE_DESKTOP_READY {"origin":"https://example.com","capability":"abc"}',
      ),
    ).toThrow("loopback");
  });

  it("assembles a split handshake and stops only its tracked child", async () => {
    const child = new FakeChild();
    let receivedOptions: Parameters<SpawnGateway>[2] | undefined;
    const spawnGateway: SpawnGateway = (_file, _args, options) => {
      receivedOptions = options;
      return child;
    };
    const gateway = new GatewayProcess(spawnGateway);

    const starting = gateway.start({
      pythonExecutable: "python",
      workspace: "D:\\repo",
      timeoutMs: 1000,
      environment: { FORGE_PROVIDER_DEMO_API_KEY: "top-secret" },
    });
    child.stdout.write("FORGE_DESKTOP_");
    child.stdout.write(
      'READY {"origin":"http://127.0.0.1:43210","capability":"abc_123"}\n',
    );

    await expect(starting).resolves.toEqual({
      origin: "http://127.0.0.1:43210",
      capability: "abc_123",
    });
    expect(gateway.state).toBe("ready");
    expect(receivedOptions?.env?.FORGE_PROVIDER_DEMO_API_KEY).toBe("top-secret");

    await gateway.stop();

    expect(child.killed).toBe(true);
    expect(gateway.state).toBe("stopped");
  });

  it("fails closed when the gateway never emits a handshake", async () => {
    const child = new FakeChild();
    const gateway = new GatewayProcess(() => child);

    await expect(
      gateway.start({ pythonExecutable: "python", workspace: "D:\\repo", timeoutMs: 5 }),
    ).rejects.toThrow("timed out");
    expect(child.killed).toBe(true);
    expect(gateway.state).toBe("failed");
  });

  it("surfaces an untrusted project challenge without treating it as a handshake", async () => {
    const child = new FakeChild();
    const gateway = new GatewayProcess(() => child);
    const starting = gateway.start({
      pythonExecutable: "python",
      workspace: "D:\\repo",
      timeoutMs: 1000,
    });

    child.stdout.write('FORGE_DESKTOP_TRUST_REQUIRED {"workspace":"D:\\\\repo"}\n');

    await expect(starting).rejects.toMatchObject({
      name: "GatewayTrustRequiredError",
      workspace: "D:\\repo",
    });
    expect(child.killed).toBe(true);
  });
});
