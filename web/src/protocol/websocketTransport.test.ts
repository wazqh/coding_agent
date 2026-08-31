import { vi } from "vitest";

import type { ConnectionState, ViewEvent } from "./types";
import { parseViewEvent, WebSocketTransport } from "./websocketTransport";

const valid = {
  protocol_version: 2,
  type: "message.delta",
  seq: 4,
  session_id: "a".repeat(24),
  turn_id: "turn-1",
  data: { delta: "hello" },
};

test("accepts a closed, valid semantic event", () => {
  expect(parseViewEvent(valid)).toEqual(valid);
});

test("accepts bounded live turn progress and rejects malformed steps", () => {
  const progress = {
    ...valid,
    type: "turn.progress",
    data: { status: "executing", step: 3, tool: "read_file" },
  };

  expect(parseViewEvent(progress)).toEqual(progress);
  expect(parseViewEvent({ ...progress, data: { status: "executing", step: -1 } })).toBeNull();
});

test("rejects unknown events before they can advance the store sequence", () => {
  expect(parseViewEvent({ ...valid, type: "future.event", seq: 999 })).toBeNull();
  expect(parseViewEvent({ ...valid, data: { delta: 42 } })).toBeNull();
  expect(parseViewEvent({ ...valid, session_id: "not-a-session" })).toBeNull();
});

test("rejects invalid snapshot permissions", () => {
  expect(
    parseViewEvent({
      ...valid,
      type: "snapshot",
      data: { permissions: "unrestricted", busy: false },
    }),
  ).toBeNull();
});

test("rejects malformed sessions, changes, and file previews", () => {
  expect(
    parseViewEvent({
      ...valid,
      type: "snapshot",
      data: { sessions: [{ id: "wrong", title: "task" }] },
    }),
  ).toBeNull();
  expect(
    parseViewEvent({
      ...valid,
      type: "changes.updated",
      data: { changes: [{ path: "demo.py", additions: -1, deletions: 0, diff: "" }] },
    }),
  ).toBeNull();
  expect(
    parseViewEvent({
      ...valid,
      type: "file.previewed",
      data: { path: "demo.py", language: "python", size: -1, text: "" },
    }),
  ).toBeNull();
});

test("accepts verification lifecycle events", () => {
  const started = { ...valid, type: "verification.started", data: {} };
  const finished = {
    ...valid,
    type: "verification.finished",
    data: { status: "not_configured", manual: false },
  };

  expect(parseViewEvent(started)).toEqual(started);
  expect(parseViewEvent(finished)).toEqual(finished);
  expect(parseViewEvent({ ...finished, data: { status: 400 } })).toBeNull();
});

test("validates live file change records before updating the Diff panel", () => {
  const recorded = {
    ...valid,
    type: "change.recorded",
    data: {
      id: "a".repeat(32),
      path: "src/new.py",
      kind: "created",
      additions: 1,
      deletions: 0,
      diff: "--- a/src/new.py\n+++ b/src/new.py\n@@ -0,0 +1 @@\n+new\n",
    },
  };

  expect(parseViewEvent(recorded)).toEqual(recorded);
  expect(parseViewEvent({ ...recorded, data: { ...recorded.data, kind: "deleted" } })).toBeNull();
  expect(parseViewEvent({ ...recorded, data: { ...recorded.data, additions: -1 } })).toBeNull();
});

test("accepts a structured skill draft and rejects malformed drafts", () => {
  const drafted = {
    ...valid,
    type: "skill.drafted",
    data: {
      draft: {
        name: "boundary-review",
        description: "Review workspace boundaries.",
        instructions: "# Workflow\n\nReview the change.",
        generated_by: "model",
      },
    },
  };

  expect(parseViewEvent(drafted)).toEqual(drafted);
  expect(parseViewEvent({ ...drafted, data: { draft: "invalid" } })).toBeNull();
});

test("batches deltas for 50ms and flushes before a non-delta event", () => {
  vi.useFakeTimers();
  const transport = new WebSocketTransport();
  const events: ViewEvent[] = [];
  transport.subscribe((event) => events.push(event));
  const receive = (transport as unknown as { handleMessage(raw: unknown): void }).handleMessage.bind(
    transport,
  );

  receive(JSON.stringify(valid));
  receive(JSON.stringify({ ...valid, seq: 5, data: { delta: " world" } }));
  expect(events).toEqual([]);
  vi.advanceTimersByTime(50);
  expect(events).toHaveLength(1);
  expect(events[0].data.delta).toBe("hello world");

  receive(JSON.stringify({ ...valid, seq: 6, data: { delta: "!" } }));
  receive(
    JSON.stringify({
      ...valid,
      type: "turn.finished",
      seq: 7,
      data: { status: "completed" },
    }),
  );
  expect(events.map((event) => event.type)).toEqual([
    "message.delta",
    "message.delta",
    "turn.finished",
  ]);
  vi.useRealTimers();
});

test("publishes connection state changes", () => {
  const transport = new WebSocketTransport();
  const statuses: ConnectionState[] = [];
  transport.subscribeStatus((status) => statuses.push(status));

  const emitStatus = (
    transport as unknown as { emitStatus(status: ConnectionState): void }
  ).emitStatus.bind(transport);
  emitStatus("connecting");
  emitStatus("connected");
  emitStatus("disconnected");

  expect(statuses).toEqual(["connecting", "connected", "disconnected"]);
});

test("retries transient startup handshake failures before publishing an error", async () => {
  vi.useFakeTimers();
  const transport = new WebSocketTransport();
  const statuses: ConnectionState[] = [];
  transport.subscribeStatus((status) => statuses.push(status));
  const open = vi.spyOn(
    transport as unknown as { open(): Promise<void> },
    "open",
  )
    .mockRejectedValueOnce(new Error("gateway is still switching"))
    .mockRejectedValueOnce(new Error("controller socket is closing"))
    .mockResolvedValueOnce();

  const connecting = transport.connect();
  await vi.runAllTimersAsync();
  await connecting;

  expect(open).toHaveBeenCalledTimes(3);
  expect(statuses).toEqual(["connecting"]);
  expect(statuses).not.toContain("error");
  vi.useRealTimers();
});
