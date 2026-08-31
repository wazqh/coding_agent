export type PermissionMode = "prompt" | "auto" | "read-only";
export type ConnectionState = "disconnected" | "connecting" | "connected" | "error";

export type ViewEventType =
  | "snapshot"
  | "turn.started"
  | "turn.progress"
  | "message.delta"
  | "message.final"
  | "activity.upsert"
  | "approval.requested"
  | "approval.resolved"
  | "plan.updated"
  | "change.recorded"
  | "context.updated"
  | "turn.finished"
  | "verification.started"
  | "verification.finished"
  | "error"
  | "file.previewed"
  | "changes.updated"
  | "runtime.updated"
  | "command.completed"
  | "completion.updated"
  | "model.catalog.updated"
  | "memory.updated"
  | "skills.updated"
  | "skill.drafted"
  | "context.compacted";

export interface ViewEvent {
  protocol_version: 2;
  type: ViewEventType;
  seq: number;
  session_id: string;
  turn_id: string | null;
  data: Record<string, unknown>;
}

export interface CompletionItem {
  kind: "command" | "file" | "skill" | "argument";
  label: string;
  insert_text: string;
  description: string;
  replace_start: number;
  replace_end: number;
}

export type ApprovalDecision = "allow_once" | "allow_session" | "deny";

export interface Transport {
  connect(): Promise<void>;
  request(type: string, payload?: Record<string, unknown>): boolean;
  subscribe(listener: (event: ViewEvent) => void): () => void;
  subscribeStatus(listener: (status: ConnectionState) => void): () => void;
  close(): void;
}
