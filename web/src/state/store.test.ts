import { createAgentStore } from "./store";

const sessionId = "a".repeat(24);

test("reduces ordered turn events and ignores duplicate sequence numbers", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;

  apply({
    protocol_version: 2,
    type: "snapshot",
    seq: 1,
    session_id: sessionId,
    turn_id: null,
    data: {
      workspace_name: "coding_agent",
      workspace_path: "D:\\codes\\coding_agent",
      model: "gemini-flash",
      permissions: "prompt",
      context_window: 1000,
      busy: false,
    },
  });
  apply({
    protocol_version: 2,
    type: "turn.started",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { task: "fix tests" },
  });
  apply({
    protocol_version: 2,
    type: "message.delta",
    seq: 3,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { delta: "Done" },
  });
  apply({
    protocol_version: 2,
    type: "message.delta",
    seq: 4,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { delta: "." },
  });
  apply({
    protocol_version: 2,
    type: "message.delta",
    seq: 4,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { delta: " duplicate" },
  });
  apply({
    protocol_version: 2,
    type: "turn.finished",
    seq: 5,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { status: "completed", reason: "" },
  });

  const state = store.getState();
  expect(state.busy).toBe(false);
  expect(state.config?.model).toBe("gemini-flash");
  expect(state.items.map((item) => item.kind)).toEqual(["user", "assistant", "completion"]);
  expect(state.items[1]).toMatchObject({ content: "Done.", streaming: false });
  expect(state.items[2]).toMatchObject({ validationStatus: "not_run" });
});

test("tracks validation outcome for the completed turn", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "activity.upsert",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-validated",
    data: {
      activity_id: "test:1",
      kind: "validation",
      title: "运行验证",
      status: "completed",
      summary: "24 passed",
    },
  });
  apply({
    protocol_version: 2,
    type: "turn.finished",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-validated",
    data: { status: "completed" },
  });

  expect(store.getState().items.at(-1)).toMatchObject({
    kind: "completion",
    validationStatus: "passed",
  });
});

test("uses the latest validation result after the agent recovers", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  for (const [seq, activityId, status] of [
    [1, "test:first", "failed"],
    [2, "test:retry", "completed"],
  ] as const) {
    apply({
      protocol_version: 2,
      type: "activity.upsert",
      seq,
      session_id: sessionId,
      turn_id: "turn-recovered",
      data: {
        activity_id: activityId,
        kind: "validation",
        title: "运行验证",
        status,
        summary: status,
      },
    });
  }
  apply({
    protocol_version: 2,
    type: "turn.finished",
    seq: 3,
    session_id: sessionId,
    turn_id: "turn-recovered",
    data: { status: "completed" },
  });

  expect(store.getState().items.at(-1)).toMatchObject({ validationStatus: "passed" });
});

test("upserts activities and stores approval ids as opaque values", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;

  apply({
    protocol_version: 2,
    type: "activity.upsert",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-1",
    data: {
      activity_id: "routine:turn-1",
      kind: "workspace_check",
      title: "检查工作区",
      status: "running",
      count: 1,
      summary: "searching",
    },
  });
  apply({
    protocol_version: 2,
    type: "activity.upsert",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-1",
    data: {
      activity_id: "routine:turn-1",
      kind: "workspace_check",
      title: "检查工作区",
      status: "completed",
      count: 2,
      summary: "found 3 matches",
    },
  });
  apply({
    protocol_version: 2,
    type: "approval.requested",
    seq: 3,
    session_id: sessionId,
    turn_id: "turn-1",
    data: {
      approval_id: "approval-1",
      request: {
        action: "run_command",
        subject: "pytest -q",
        summary: "run tests",
        diff: null,
      },
    },
  });

  const state = store.getState();
  expect(state.items).toHaveLength(2);
  expect(state.items[0]).toMatchObject({
    kind: "activity",
    activityId: "routine:turn-1",
    count: 2,
    status: "completed",
  });
  expect(state.items[1]).toMatchObject({ kind: "approval", approvalId: "approval-1" });
});

test("merges an approval into the operation card with the same stable id", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "activity.upsert",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-operation",
    data: {
      activity_id: "tool:write-1",
      operation_id: "write-1",
      kind: "file_change",
      title: "修改文件",
      status: "running",
      summary: "README.md",
    },
  });
  apply({
    protocol_version: 2,
    type: "approval.requested",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-operation",
    data: {
      approval_id: "approval-write",
      operation_id: "write-1",
      request: {
        action: "edit_file",
        subject: "README.md",
        summary: "edit README.md",
      },
    },
  });
  apply({
    protocol_version: 2,
    type: "approval.resolved",
    seq: 3,
    session_id: sessionId,
    turn_id: "turn-operation",
    data: {
      approval_id: "approval-write",
      operation_id: "write-1",
      decision: "allow_once",
    },
  });

  expect(store.getState().items).toHaveLength(1);
  expect(store.getState().items[0]).toMatchObject({
    kind: "activity",
    operationId: "write-1",
    approval: {
      approvalId: "approval-write",
      resolved: true,
      decision: "allow_once",
    },
  });
});

test("keeps accepted events as authority and reduces real usage fields", () => {
  const store = createAgentStore();
  store.getState().applyEvent({
    protocol_version: 2,
    type: "snapshot",
    seq: 1,
    session_id: sessionId,
    turn_id: null,
    data: { context_window: 1000 },
  });
  store.getState().applyEvent({
    protocol_version: 2,
    type: "context.updated",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { prompt_tokens: 400, completion_tokens: 25, total_tokens: 425 },
  });

  const state = store.getState();
  expect(state.events).toHaveLength(2);
  expect(state.context).toEqual({
    inputTokens: 400,
    contextWindow: 1000,
    percentUsed: 40,
    action: "",
  });
});

test("preserves usage while applying a compact action", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "context.updated",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { prompt_tokens: 400, context_window: 1000 },
  });
  apply({
    protocol_version: 2,
    type: "context.updated",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { action: "compacted" },
  });

  expect(store.getState().context).toEqual({
    inputTokens: 400,
    contextWindow: 1000,
    percentUsed: 40,
    action: "compacted",
  });
});

test.each([
  [153, 100],
  [-8, 0],
] as const)("clamps explicit context usage %s to %s for the UI", (reported, expected) => {
  const store = createAgentStore();
  store.getState().applyEvent({
    protocol_version: 2,
    type: "context.updated",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { percent_used: reported },
  });

  expect(store.getState().context?.percentUsed).toBe(expected);
});

test("disconnect cancels unresolved approval and interrupts the active turn", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "turn.started",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-approval",
    data: { task: "执行命令" },
  });
  apply({
    protocol_version: 2,
    type: "approval.requested",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-approval",
    data: {
      approval_id: "approval-disconnect",
      request: { action: "run_command", subject: "pytest -q", summary: "运行测试" },
    },
  });

  store.getState().setConnection("disconnected");

  const state = store.getState();
  expect(state.busy).toBe(false);
  expect(state.items).toContainEqual(
    expect.objectContaining({
      kind: "approval",
      approvalId: "approval-disconnect",
      resolved: true,
      decision: "cancelled",
    }),
  );
  expect(state.items.at(-1)).toMatchObject({
    kind: "completion",
    status: "interrupted",
    validationStatus: "not_run",
  });
});

test("disconnect keeps the active turn id and real completion replaces the synthetic one", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "turn.started",
    seq: 1,
    session_id: sessionId,
    turn_id: null,
    data: { task: "长任务" },
  });
  apply({
    protocol_version: 2,
    type: "activity.upsert",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-streaming",
    data: {
      activity_id: "test:running",
      kind: "validation",
      title: "运行验证",
      status: "running",
      summary: "pytest -q",
    },
  });
  store.getState().setConnection("disconnected");

  expect(store.getState().items.at(-1)).toMatchObject({
    kind: "completion",
    turnId: "turn-streaming",
    status: "interrupted",
    validationStatus: "incomplete",
  });

  apply({
    protocol_version: 2,
    type: "turn.finished",
    seq: 3,
    session_id: sessionId,
    turn_id: "turn-streaming",
    data: { status: "cancelled", reason: "cancelled" },
  });
  const completions = store
    .getState()
    .items.filter((item) => item.kind === "completion" && item.turnId === "turn-streaming");
  expect(completions).toHaveLength(1);
  expect(completions[0]).toMatchObject({ status: "cancelled" });
});

test("real completion replaces a null-id synthetic completion after an immediate disconnect", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "turn.started",
    seq: 1,
    session_id: sessionId,
    turn_id: null,
    data: { task: "立即断线" },
  });
  store.getState().setConnection("disconnected");
  expect(store.getState().items.at(-1)).toMatchObject({
    kind: "completion",
    turnId: null,
    status: "interrupted",
  });

  apply({
    protocol_version: 2,
    type: "turn.finished",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-late-id",
    data: { status: "cancelled" },
  });

  const completions = store.getState().items.filter((item) => item.kind === "completion");
  expect(completions).toHaveLength(1);
  expect(completions[0]).toMatchObject({ turnId: "turn-late-id", status: "cancelled" });
});

test("snapshot replaces the timeline on session switch and stores workspace sessions", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "message.final",
    seq: 1,
    session_id: sessionId,
    turn_id: null,
    data: { role: "assistant", content: "旧会话" },
  });
  apply({
    protocol_version: 2,
    type: "snapshot",
    seq: 2,
    session_id: "b".repeat(24),
    turn_id: null,
    data: {
      replace_timeline: true,
      sessions: [
        {
          id: "b".repeat(24),
          title: "新任务",
          updated_at: "2026-08-29T10:00:00Z",
          model: "gemini-flash",
        },
      ],
    },
  });

  expect(store.getState().items).toEqual([]);
  expect(store.getState().sessions[0]).toMatchObject({
    id: "b".repeat(24),
    title: "新任务",
    model: "gemini-flash",
  });
});

test("stores change review and safe file preview events", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "changes.updated",
    seq: 1,
    session_id: sessionId,
    turn_id: null,
    data: {
      changes: [
        {
          id: "change-1",
          path: "src/demo.py",
          additions: 2,
          deletions: 1,
          diff: "--- a/src/demo.py\n+++ b/src/demo.py\n",
        },
      ],
    },
  });
  apply({
    protocol_version: 2,
    type: "file.previewed",
    seq: 2,
    session_id: sessionId,
    turn_id: null,
    data: { path: "src/demo.py", language: "python", size: 12, text: "answer = 42" },
  });

  expect(store.getState().changes[0]).toMatchObject({ path: "src/demo.py", additions: 2 });
  expect(store.getState().filePreview).toEqual({
    path: "src/demo.py",
    language: "python",
    size: 12,
    text: "answer = 42",
  });
});

test("adds a newly created file as soon as its change event arrives", () => {
  const store = createAgentStore();

  store.getState().applyEvent({
    protocol_version: 2,
    type: "change.recorded",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-1",
    data: {
      id: "a".repeat(32),
      path: "src/new.py",
      kind: "created",
      additions: 1,
      deletions: 0,
      diff: "--- a/src/new.py\n+++ b/src/new.py\n@@ -0,0 +1 @@\n+hello\n",
    },
  });

  expect(store.getState().changes).toEqual([
    expect.objectContaining({
      id: "a".repeat(32),
      path: "src/new.py",
      kind: "created",
      additions: 1,
    }),
  ]);
});

test("uses the first task to title a newly created session immediately", () => {
  const store = createAgentStore();
  store.getState().applyEvent({
    protocol_version: 2,
    type: "snapshot",
    seq: 1,
    session_id: sessionId,
    turn_id: null,
    data: {
      busy: false,
      model: "gemini-flash",
      sessions: [{ id: sessionId, title: "", updated_at: "", model: "gemini-flash" }],
    },
  });
  store.getState().applyEvent({
    protocol_version: 2,
    type: "turn.started",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-title",
    data: { task: "修复登录测试并运行验证" },
  });

  expect(store.getState().sessions[0].title).toBe("修复登录测试并运行验证");
});

test("keeps plan updates isolated to their originating turn", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "plan.updated",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-1",
    data: { plan: [{ step: "检查旧任务", status: "completed" }] },
  });
  apply({
    protocol_version: 2,
    type: "plan.updated",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-2",
    data: { plan: [{ step: "检查新任务", status: "in_progress" }] },
  });
  apply({
    protocol_version: 2,
    type: "plan.updated",
    seq: 3,
    session_id: sessionId,
    turn_id: "turn-2",
    data: { plan: [{ step: "实现新任务", status: "completed" }] },
  });

  const plans = store.getState().items.filter((item) => item.kind === "plan");
  expect(plans).toEqual([
    { id: "plan:turn-1", kind: "plan", steps: [{ step: "检查旧任务", status: "completed" }] },
    { id: "plan:turn-2", kind: "plan", steps: [{ step: "实现新任务", status: "completed" }] },
  ]);
});

test("stores live turn progress until the turn finishes", () => {
  const store = createAgentStore();
  const apply = store.getState().applyEvent;
  apply({
    protocol_version: 2,
    type: "turn.progress",
    seq: 1,
    session_id: sessionId,
    turn_id: "turn-progress",
    data: { status: "executing", step: 3, tool: "read_file" },
  });

  expect(store.getState().progress).toEqual({ status: "executing", step: 3, tool: "read_file" });

  apply({
    protocol_version: 2,
    type: "turn.finished",
    seq: 2,
    session_id: sessionId,
    turn_id: "turn-progress",
    data: { status: "completed" },
  });
  expect(store.getState().progress).toBeNull();
});
