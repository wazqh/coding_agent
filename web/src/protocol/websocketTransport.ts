import type { ConnectionState, Transport, ViewEvent } from "./types";

const protocolVersion = 2;
const sessionPattern = /^[0-9a-f]{24}$/;
const eventTypes = new Set([
  "snapshot",
  "turn.started",
  "turn.progress",
  "message.delta",
  "message.final",
  "activity.upsert",
  "approval.requested",
  "approval.resolved",
  "plan.updated",
  "change.recorded",
  "context.updated",
  "turn.finished",
  "error",
  "file.previewed",
  "changes.updated",
  "runtime.updated",
  "command.completed",
  "completion.updated",
  "model.catalog.updated",
  "memory.updated",
  "skills.updated",
  "context.compacted",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasStrings(data: Record<string, unknown>, names: string[]): boolean {
  return names.every((name) => typeof data[name] === "string");
}

function isNonNegativeInteger(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isSessionSummary(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    sessionPattern.test(value.id) &&
    hasStrings(value, ["title", "updated_at", "model"])
  );
}

function isChangeSummary(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    hasStrings(value, ["id", "path", "diff"]) &&
    typeof value.path === "string" &&
    value.path.length > 0 &&
    isNonNegativeInteger(value.additions) &&
    isNonNegativeInteger(value.deletions)
  );
}

function isEventData(type: string, data: Record<string, unknown>): boolean {
  if (type === "snapshot") {
    const permission = data.permissions;
    return (
      (permission === undefined || ["prompt", "auto", "read-only"].includes(String(permission))) &&
      (data.busy === undefined || typeof data.busy === "boolean") &&
      (data.sessions === undefined ||
        (Array.isArray(data.sessions) && data.sessions.every(isSessionSummary)))
    );
  }
  if (type === "turn.started") return hasStrings(data, ["task"]);
  if (type === "turn.progress") {
    return (
      typeof data.status === "string" &&
      (data.step === undefined || isNonNegativeInteger(data.step)) &&
      (data.tool === undefined || typeof data.tool === "string")
    );
  }
  if (type === "message.delta") return hasStrings(data, ["delta"]);
  if (type === "message.final") {
    return ["user", "assistant"].includes(String(data.role)) && hasStrings(data, ["content"]);
  }
  if (type === "activity.upsert") {
    return hasStrings(data, ["activity_id", "kind", "title", "status", "summary"]);
  }
  if (type === "approval.requested") {
    return (
      typeof data.approval_id === "string" &&
      isRecord(data.request) &&
      hasStrings(data.request, ["action", "subject", "summary"])
    );
  }
  if (type === "approval.resolved") {
    return hasStrings(data, ["approval_id", "decision"]);
  }
  if (type === "plan.updated") return Array.isArray(data.plan);
  if (type === "turn.finished") return typeof data.status === "string";
  if (type === "error") return hasStrings(data, ["severity", "message"]);
  if (type === "file.previewed") {
    return (
      hasStrings(data, ["path", "language", "text"]) &&
      typeof data.path === "string" &&
      data.path.length > 0 &&
      isNonNegativeInteger(data.size)
    );
  }
  if (type === "changes.updated") {
    return Array.isArray(data.changes) && data.changes.every(isChangeSummary);
  }
  if (type === "runtime.updated") return isRecord(data.runtime);
  if (type === "command.completed") return hasStrings(data, ["command", "status"]);
  if (type === "completion.updated") {
    return (
      hasStrings(data, ["request_id", "text"]) &&
      isNonNegativeInteger(data.cursor) &&
      Array.isArray(data.items) &&
      data.items.every((value) => {
        if (!isRecord(value)) return false;
        return (
          ["command", "file", "skill", "argument"].includes(String(value.kind)) &&
          hasStrings(value, ["label", "insert_text", "description"]) &&
          isNonNegativeInteger(value.replace_start) &&
          isNonNegativeInteger(value.replace_end)
        );
      })
    );
  }
  if (type === "model.catalog.updated") return isRecord(data.catalog);
  if (type === "memory.updated") return isRecord(data.memory);
  if (type === "skills.updated") return isRecord(data.skills);
  if (type === "context.compacted") return isRecord(data.result);
  return type === "change.recorded" || type === "context.updated";
}

export function parseViewEvent(value: unknown): ViewEvent | null {
  if (typeof value !== "object" || value === null) return null;
  const frame = value as Partial<ViewEvent>;
  const valid =
    frame.protocol_version === protocolVersion &&
    typeof frame.type === "string" &&
    eventTypes.has(frame.type) &&
    Number.isInteger(frame.seq) &&
    Number(frame.seq) >= 1 &&
    typeof frame.session_id === "string" &&
    sessionPattern.test(frame.session_id) &&
    (frame.turn_id === null ||
      (typeof frame.turn_id === "string" && frame.turn_id.length <= 128)) &&
    isRecord(frame.data) &&
    isEventData(frame.type, frame.data);
  return valid ? (value as ViewEvent) : null;
}

export class WebSocketTransport implements Transport {
  private socket: WebSocket | null = null;
  private listeners = new Set<(event: ViewEvent) => void>();
  private statusListeners = new Set<(status: ConnectionState) => void>();
  private requestCounter = 0;
  private pendingDelta: ViewEvent | null = null;
  private deltaTimer: number | null = null;
  private connectPromise: Promise<void> | null = null;

  async connect(): Promise<void> {
    if (this.socket?.readyState === WebSocket.OPEN) return;
    if (this.connectPromise) return this.connectPromise;
    this.emitStatus("connecting");
    const attempt = this.open();
    this.connectPromise = attempt;
    try {
      await attempt;
    } catch (error) {
      if (this.connectPromise === attempt) this.connectPromise = null;
      this.emitStatus("error");
      throw error;
    }
  }

  private async open(): Promise<void> {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const capability = fragment.get("capability");
    if (capability) {
      const response = await fetch("/api/bootstrap", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-Forge-Capability": capability },
      });
      if (!response.ok) throw new Error("无法验证本地 Web UI 启动凭据");
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    }

    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${window.location.host}/ws`);
    this.socket = socket;
    await new Promise<void>((resolve, reject) => {
      socket.addEventListener("open", () => resolve(), { once: true });
      socket.addEventListener("error", () => reject(new Error("无法连接本地 Agent 运行时")), {
        once: true,
      });
    });
    socket.addEventListener("message", (message) => this.handleMessage(message.data));
    this.emitStatus("connected");
    socket.addEventListener("close", () => {
      this.flushDelta();
      if (this.socket === socket) {
        this.socket = null;
        this.connectPromise = null;
      }
      this.emitStatus("disconnected");
    });
    this.request("initialize", { last_seq: 0 });
  }

  request(type: string, payload: Record<string, unknown> = {}): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.requestCounter += 1;
    this.socket.send(
      JSON.stringify({
        protocol_version: protocolVersion,
        type,
        request_id: `web-${this.requestCounter}`,
        ...payload,
      }),
    );
    return true;
  }

  subscribe(listener: (event: ViewEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  subscribeStatus(listener: (status: ConnectionState) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  close(): void {
    this.flushDelta();
    this.socket?.close(1000, "client closed");
    this.socket = null;
    this.connectPromise = null;
  }

  private handleMessage(raw: unknown): void {
    if (typeof raw !== "string") return;
    let value: unknown;
    try {
      value = JSON.parse(raw);
    } catch {
      return;
    }
    const event = parseViewEvent(value);
    if (!event) return;
    if (event.type !== "message.delta") {
      this.flushDelta();
      this.emit(event);
      return;
    }
    const delta = String(event.data.delta);
    if (this.pendingDelta?.turn_id === event.turn_id) {
      this.pendingDelta = {
        ...event,
        data: { delta: `${String(this.pendingDelta.data.delta ?? "")}${delta}` },
      };
    } else {
      this.flushDelta();
      this.pendingDelta = { ...event, data: { delta } };
    }
    if (this.deltaTimer === null) {
      this.deltaTimer = window.setTimeout(() => this.flushDelta(), 50);
    }
  }

  private flushDelta(): void {
    if (this.deltaTimer !== null) window.clearTimeout(this.deltaTimer);
    this.deltaTimer = null;
    if (this.pendingDelta) this.emit(this.pendingDelta);
    this.pendingDelta = null;
  }

  private emit(event: ViewEvent): void {
    for (const listener of this.listeners) listener(event);
  }

  private emitStatus(status: ConnectionState): void {
    for (const listener of this.statusListeners) listener(status);
  }
}
