import { createStore } from "zustand/vanilla";

import type { CompletionItem, ConnectionState, PermissionMode, ViewEvent } from "../protocol/types";

export interface RuntimeConfig {
  workspaceName: string;
  workspacePath: string;
  model: string;
  permissions: PermissionMode;
  contextWindow: number;
}

export interface ContextUsage {
  inputTokens: number;
  contextWindow: number;
  percentUsed: number;
  action: string;
}

export interface SessionSummary {
  id: string;
  title: string;
  updatedAt: string;
  model: string;
}

export interface ChangeSummary {
  id: string;
  path: string;
  additions: number;
  deletions: number;
  diff: string;
}

export interface FilePreviewData {
  path: string;
  language: string;
  size: number;
  text: string;
}

export interface ProjectSummary {
  name: string;
  path: string;
  current: boolean;
  sessions: SessionSummary[];
}

export interface CompletionState {
  text: string;
  cursor: number;
  items: CompletionItem[];
}

export interface TurnProgress {
  status: string;
  step: number;
  tool?: string;
}

export interface RuntimeState {
  workspace?: string;
  workspace_name?: string;
  session_id?: string;
  lifecycle?: string;
  permissions?: PermissionMode;
  session_grants?: number;
  steps?: {
    current?: number;
    configured_default?: number;
    overridden?: boolean;
    minimum?: number;
    maximum?: number;
  };
  model?: { provider?: string; id?: string };
  context?: { estimated_tokens?: number; context_window?: number; percent_used?: number };
  resources?: Record<string, unknown>;
  plan?: Array<Record<string, unknown>>;
}

export interface ModelCatalogState {
  active?: { provider?: string; id?: string };
  providers?: Array<{
    name?: string;
    default_model?: string;
    models?: string[];
    active?: boolean;
  }>;
}

export interface MemoryState {
  enabled?: boolean;
  items?: Array<Record<string, unknown>>;
}

export interface SkillsState {
  items?: Array<Record<string, unknown>>;
  active?: string[];
  diagnostics?: string[];
}

export type TimelineItem =
  | { id: string; kind: "user"; content: string }
  | { id: string; kind: "assistant"; content: string; streaming: boolean }
  | {
      id: string;
      kind: "activity";
      turnId?: string | null;
      activityId: string;
      activityKind: string;
      title: string;
      summary: string;
      status: string;
      count?: number;
      detail?: unknown;
    }
  | {
      id: string;
      kind: "approval";
      turnId?: string | null;
      approvalId: string;
      action: string;
      subject: string;
      summary: string;
      diff?: string;
      resolved: boolean;
      decision?: string;
    }
  | { id: string; kind: "plan"; steps: Array<Record<string, unknown>> }
  | { id: string; kind: "error"; message: string; severity: string }
  | {
      id: string;
      kind: "completion";
      turnId?: string | null;
      status: string;
      reason: string;
      validationStatus: "passed" | "failed" | "incomplete" | "not_run";
    };

export interface AgentState {
  lastSeq: number;
  sessionId: string | null;
  activeTurnId: string | null;
  progress: TurnProgress | null;
  busy: boolean;
  config: RuntimeConfig | null;
  connection: ConnectionState;
  context: ContextUsage | null;
  sessions: SessionSummary[];
  projects: ProjectSummary[];
  changes: ChangeSummary[];
  filePreview: FilePreviewData | null;
  completion: CompletionState | null;
  runtime: RuntimeState | null;
  modelCatalog: ModelCatalogState | null;
  memoryState: MemoryState | null;
  skillsState: SkillsState | null;
  events: ViewEvent[];
  items: TimelineItem[];
  applyEvent: (event: ViewEvent) => void;
  setConnection: (connection: ConnectionState) => void;
  clearView: () => void;
  reset: () => void;
}

const initialState = {
  lastSeq: 0,
  sessionId: null,
  activeTurnId: null,
  progress: null as TurnProgress | null,
  busy: false,
  config: null,
  connection: "disconnected" as ConnectionState,
  context: null as ContextUsage | null,
  sessions: [] as SessionSummary[],
  projects: [] as ProjectSummary[],
  changes: [] as ChangeSummary[],
  filePreview: null as FilePreviewData | null,
  completion: null as CompletionState | null,
  runtime: null as RuntimeState | null,
  modelCatalog: null as ModelCatalogState | null,
  memoryState: null as MemoryState | null,
  skillsState: null as SkillsState | null,
  events: [] as ViewEvent[],
  items: [] as TimelineItem[],
};

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

function clampPercent(value: number, fallback = 0): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.max(0, Math.min(100, value));
}

function validationStatus(
  items: TimelineItem[],
  turnId: string | null,
): "passed" | "failed" | "incomplete" | "not_run" {
  const validations = items.filter(
    (item): item is Extract<TimelineItem, { kind: "activity" }> =>
      item.kind === "activity" && item.activityKind === "validation" && item.turnId === turnId,
  );
  const latest = validations.at(-1);
  if (latest?.status === "failed") return "failed";
  if (latest?.status === "running") return "incomplete";
  if (latest?.status === "completed") return "passed";
  return "not_run";
}

export function createAgentStore() {
  return createStore<AgentState>((set) => ({
    ...initialState,
    reset: () => set(initialState),
    clearView: () => set({ items: [], changes: [], filePreview: null }),
    setConnection: (connection) =>
      set((state) => {
        if (connection !== "disconnected" || !state.busy) return { connection };
        const turnId = state.activeTurnId;
        const items = state.items.map((item) =>
          item.kind === "approval" && !item.resolved
            ? { ...item, resolved: true, decision: "cancelled" }
            : item,
        );
        return {
          connection,
          busy: false,
          activeTurnId: null,
          progress: null,
          items: [
            ...items,
            {
              id: `completion:disconnect:${state.lastSeq}`,
              kind: "completion",
              turnId,
              status: "interrupted",
              reason: "连接中断，任务已取消",
              validationStatus: validationStatus(items, turnId),
            },
          ],
        };
      }),
    applyEvent: (event) =>
      set((state) => {
        if (event.seq <= state.lastSeq) return state;
        const base = {
          ...state,
          lastSeq: event.seq,
          sessionId: event.session_id,
          activeTurnId:
            state.busy && state.activeTurnId === null && event.turn_id !== null
              ? event.turn_id
              : state.activeTurnId,
          events: [...state.events, event],
        };

        if (event.type === "snapshot") {
          const runtime = record(event.data.runtime);
          const normalizeSession = (value: unknown): SessionSummary => {
                const item = record(value);
                return {
                  id: text(item.id),
                  title: text(item.title, "未命名任务"),
                  updatedAt: text(item.updated_at),
                  model: text(item.model),
                };
              };
          const sessions = Array.isArray(event.data.sessions)
            ? event.data.sessions.map(normalizeSession)
            : state.sessions;
          const projects = Array.isArray(event.data.projects)
            ? event.data.projects.map((value) => {
                const item = record(value);
                return {
                  name: text(item.name, "未命名项目"),
                  path: text(item.path),
                  current: item.current === true,
                  sessions: Array.isArray(item.sessions)
                    ? item.sessions.map(normalizeSession)
                    : [],
                };
              })
            : state.projects;
          return {
            ...base,
            busy: Boolean(event.data.busy),
            activeTurnId: Boolean(event.data.busy) ? state.activeTurnId : null,
            progress: Boolean(event.data.busy) ? state.progress : null,
            connection: "connected",
            config: {
              workspaceName: text(event.data.workspace_name, "当前项目"),
              workspacePath: text(event.data.workspace_path),
              model: text(event.data.model, "未连接"),
              permissions: text(event.data.permissions, "prompt") as PermissionMode,
              contextWindow: Number(event.data.context_window ?? 0),
            },
            context: {
              inputTokens: 0,
              contextWindow: Number(event.data.context_window ?? 0),
              percentUsed: 0,
              action: "",
            },
            sessions,
            projects,
            runtime: Object.keys(runtime).length ? (runtime as RuntimeState) : state.runtime,
            items: event.data.replace_timeline === true ? [] : state.items,
            changes: event.data.replace_timeline === true ? [] : state.changes,
            filePreview: event.data.replace_timeline === true ? null : state.filePreview,
          };
        }

        if (event.type === "turn.started") {
          const task = text(event.data.task);
          const sessionIndex = state.sessions.findIndex((session) => session.id === event.session_id);
          const sessions = [...state.sessions];
          if (sessionIndex >= 0 && !sessions[sessionIndex].title.trim()) {
            sessions[sessionIndex] = { ...sessions[sessionIndex], title: task.slice(0, 80) };
          } else if (sessionIndex < 0) {
            sessions.push({
              id: event.session_id,
              title: task.slice(0, 80),
              updatedAt: "",
              model: state.config?.model ?? "",
            });
          }
          return {
            ...base,
            busy: true,
            activeTurnId: event.turn_id,
            progress: { status: "thinking", step: 0 },
            sessions,
            items: [
              ...state.items,
              { id: `user:${event.seq}`, kind: "user", content: task },
            ],
          };
        }

        if (event.type === "message.delta") {
          const id = `assistant:${event.turn_id ?? event.session_id}`;
          const index = state.items.findIndex((item) => item.id === id);
          if (index < 0) {
            return {
              ...base,
              items: [
                ...state.items,
                { id, kind: "assistant", content: text(event.data.delta), streaming: true },
              ],
            };
          }
          const items = [...state.items];
          const current = items[index];
          if (current.kind === "assistant") {
            items[index] = { ...current, content: current.content + text(event.data.delta) };
          }
          return { ...base, items };
        }

        if (event.type === "message.final") {
          const role = text(event.data.role, "assistant");
          const streamId = `assistant:${event.turn_id ?? event.session_id}`;
          const streamIndex = state.items.findIndex((item) => item.id === streamId);
          if (role !== "user" && streamIndex >= 0) {
            const items = [...state.items];
            items[streamIndex] = {
              id: streamId,
              kind: "assistant",
              content: text(event.data.content),
              streaming: false,
            };
            return { ...base, items };
          }
          const item: TimelineItem =
            role === "user"
              ? { id: `message:${event.seq}`, kind: "user", content: text(event.data.content) }
              : {
                  id: `message:${event.seq}`,
                  kind: "assistant",
                  content: text(event.data.content),
                  streaming: false,
                };
          return { ...base, items: [...state.items, item] };
        }

        if (event.type === "activity.upsert") {
          const activityId = text(event.data.activity_id, `activity:${event.seq}`);
          const item: TimelineItem = {
            id: `activity:${activityId}`,
            kind: "activity",
            turnId: event.turn_id,
            activityId,
            activityKind: text(event.data.kind, "tool"),
            title: text(event.data.title, "Agent 操作"),
            summary: text(event.data.summary),
            status: text(event.data.status, "running"),
            ...(typeof event.data.count === "number" ? { count: event.data.count } : {}),
            ...(event.data.detail === undefined ? {} : { detail: event.data.detail }),
          };
          const index = state.items.findIndex(
            (current) => current.kind === "activity" && current.activityId === activityId,
          );
          if (index < 0) return { ...base, items: [...state.items, item] };
          const items = [...state.items];
          items[index] = item;
          return { ...base, items };
        }

        if (event.type === "approval.requested") {
          const request = record(event.data.request);
          return {
            ...base,
            items: [
              ...state.items,
              {
                id: `approval:${text(event.data.approval_id)}`,
                kind: "approval",
                turnId: event.turn_id,
                approvalId: text(event.data.approval_id),
                action: text(request.action),
                subject: text(request.subject),
                summary: text(request.summary),
                ...(typeof request.diff === "string" ? { diff: request.diff } : {}),
                resolved: false,
              },
            ],
          };
        }

        if (event.type === "approval.resolved") {
          const approvalId = text(event.data.approval_id);
          return {
            ...base,
            items: state.items.map((item) =>
              item.kind === "approval" && item.approvalId === approvalId
                ? { ...item, resolved: true, decision: text(event.data.decision) }
                : item,
            ),
          };
        }

        if (event.type === "plan.updated") {
          const steps = Array.isArray(event.data.plan)
            ? event.data.plan.map((step) => record(step))
            : [];
          const item: TimelineItem = { id: `plan:${event.turn_id}`, kind: "plan", steps };
          const index = state.items.findIndex((current) => current.id === item.id);
          if (index < 0) return { ...base, items: [...state.items, item] };
          const items = [...state.items];
          items[index] = item;
          return { ...base, items };
        }

        if (event.type === "context.updated") {
          const inputValue = event.data.prompt_tokens ?? event.data.context_tokens;
          const windowValue = event.data.context_window;
          const inputTokens = Number(inputValue ?? state.context?.inputTokens ?? 0);
          const contextWindow = Number(
            windowValue ?? state.context?.contextWindow ?? state.config?.contextWindow ?? 0,
          );
          const explicitPercent = Number(event.data.percent_used);
          const percentUsed = clampPercent(Number.isFinite(explicitPercent)
            ? explicitPercent
            : inputValue !== undefined || windowValue !== undefined
              ? contextWindow > 0
                ? Math.round((inputTokens * 100) / contextWindow)
                : 0
              : (state.context?.percentUsed ?? 0));
          return {
            ...base,
            context: {
              inputTokens,
              contextWindow,
              percentUsed,
              action: text(event.data.action),
            },
          };
        }

        if (event.type === "turn.progress") {
          return {
            ...base,
            activeTurnId: event.turn_id ?? state.activeTurnId,
            progress: {
              status: text(event.data.status, "thinking"),
              step: Number(event.data.step ?? 0),
              ...(typeof event.data.tool === "string" ? { tool: event.data.tool } : {}),
            },
          };
        }

        if (event.type === "completion.updated") {
          const items = Array.isArray(event.data.items)
            ? event.data.items.map((value) => {
                const item = record(value);
                return {
                  kind: text(item.kind, "command") as CompletionItem["kind"],
                  label: text(item.label),
                  insert_text: text(item.insert_text),
                  description: text(item.description),
                  replace_start: Number(item.replace_start ?? 0),
                  replace_end: Number(item.replace_end ?? 0),
                };
              })
            : [];
          return {
            ...base,
            completion: {
              text: text(event.data.text),
              cursor: Number(event.data.cursor ?? 0),
              items,
            },
          };
        }

        if (event.type === "runtime.updated") {
          const runtime = record(event.data.runtime);
          const model = record(runtime.model);
          const context = record(runtime.context);
          return {
            ...base,
            runtime: runtime as RuntimeState,
            config: {
              workspaceName: text(runtime.workspace_name, state.config?.workspaceName ?? "当前项目"),
              workspacePath: text(runtime.workspace, state.config?.workspacePath ?? ""),
              model: text(model.id, state.config?.model ?? "未连接"),
              permissions: text(runtime.permissions, state.config?.permissions ?? "prompt") as PermissionMode,
              contextWindow: Number(context.context_window ?? state.config?.contextWindow ?? 0),
            },
            context: {
              inputTokens: Number(context.estimated_tokens ?? state.context?.inputTokens ?? 0),
              contextWindow: Number(context.context_window ?? state.context?.contextWindow ?? 0),
              percentUsed: clampPercent(
                Number(context.percent_used ?? state.context?.percentUsed ?? 0),
                state.context?.percentUsed ?? 0,
              ),
              action: state.context?.action ?? "",
            },
          };
        }

        if (event.type === "model.catalog.updated") {
          return { ...base, modelCatalog: record(event.data.catalog) as ModelCatalogState };
        }

        if (event.type === "memory.updated") {
          return { ...base, memoryState: record(event.data.memory) as MemoryState };
        }

        if (event.type === "skills.updated") {
          return { ...base, skillsState: record(event.data.skills) as SkillsState };
        }

        if (event.type === "context.compacted") {
          const result = record(event.data.result);
          return {
            ...base,
            context: {
              inputTokens: Number(result.after_tokens ?? state.context?.inputTokens ?? 0),
              contextWindow: state.context?.contextWindow ?? state.config?.contextWindow ?? 0,
              percentUsed: state.context?.percentUsed ?? 0,
              action: result.changed === true ? "compacted" : "unchanged",
            },
          };
        }

        if (event.type === "error") {
          return {
            ...base,
            items: [
              ...state.items,
              {
                id: `error:${event.seq}`,
                kind: "error",
                message: text(event.data.message, "发生未知错误"),
                severity: text(event.data.severity, "error"),
              },
            ],
          };
        }

        if (event.type === "changes.updated") {
          const changes = Array.isArray(event.data.changes)
            ? event.data.changes.map((value) => {
                const item = record(value);
                return {
                  id: text(item.id),
                  path: text(item.path),
                  additions: Number(item.additions ?? 0),
                  deletions: Number(item.deletions ?? 0),
                  diff: text(item.diff),
                };
              })
            : [];
          return { ...base, changes };
        }

        if (event.type === "file.previewed") {
          return {
            ...base,
            filePreview: {
              path: text(event.data.path),
              language: text(event.data.language, "text"),
              size: Number(event.data.size ?? 0),
              text: text(event.data.text),
            },
          };
        }

        if (event.type === "turn.finished") {
          const items = state.items.map((item) =>
            item.kind === "assistant" && item.streaming ? { ...item, streaming: false } : item,
          );
          const completion: TimelineItem = {
            id: `completion:${event.turn_id ?? event.seq}`,
            kind: "completion",
            turnId: event.turn_id,
            status: text(event.data.status, "completed"),
            reason: text(event.data.reason),
            validationStatus: validationStatus(items, event.turn_id),
          };
          let completionIndex = -1;
          for (let index = items.length - 1; index >= 0; index -= 1) {
            const item = items[index];
            if (
              item.kind === "completion" &&
              (item.turnId === event.turn_id ||
                (item.turnId === null && item.status === "interrupted"))
            ) {
              completionIndex = index;
              break;
            }
          }
          if (completionIndex >= 0) items[completionIndex] = completion;
          else items.push(completion);
          return {
            ...base,
            busy: false,
            activeTurnId: null,
            progress: null,
            items,
          };
        }

        return base;
      }),
  }));
}

export const agentStore = createAgentStore();
