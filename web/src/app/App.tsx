import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useStore } from "zustand";
import type { StoreApi } from "zustand";

import { Composer } from "../components/Composer";
import { CommandGuide } from "../components/CommandGuide";
import { ConnectionTransition } from "../components/ConnectionTransition";
import { ContextDrawer } from "../components/ContextDrawer";
import type { ModelUpdateInput } from "../components/ModelManager";
import { SessionRail } from "../components/SessionRail";
import { Timeline } from "../components/Timeline";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import type { ApprovalDecision, PermissionMode, Transport } from "../protocol/types";
import { agentStore, type AgentState } from "../state/store";
import "./theme.css";

export interface AppProps {
  productName: string;
  workspaceName: string;
  workspacePath: string;
  modelName: string;
  permissions: PermissionMode;
  busy?: boolean;
  transport?: Transport;
  store?: StoreApi<AgentState>;
  desktop?: boolean;
}

export function App({
  productName,
  workspaceName,
  workspacePath,
  modelName,
  permissions,
  busy = false,
  transport,
  store,
  desktop = false,
}: AppProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerWidth, setDrawerWidth] = useState(() => {
    const stored = Number(window.localStorage.getItem("forge.inspector.width"));
    return Number.isFinite(stored) && stored >= 360 && stored <= 900 ? stored : 438;
  });
  const [railOpen, setRailOpen] = useState(false);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [drawerView, setDrawerView] = useState<
    "changes" | "run" | "settings" | "resources" | "context"
  >("changes");
  const [helpOpen, setHelpOpen] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [commandFeedback, setCommandFeedback] = useState("");
  const [addingProject, setAddingProject] = useState(false);
  const [projectFeedback, setProjectFeedback] = useState("");
  const [modelSetupOpen, setModelSetupOpen] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [connectionActivity, setConnectionActivity] = useState<
    "startup" | "model-restart" | "workspace-restart"
  >("startup");
  const activeStore = store ?? agentStore;
  const runtimeBusy = useStore(activeStore, (state) => state.busy);
  const progress = useStore(activeStore, (state) => state.progress);
  const runtimeConfig = useStore(activeStore, (state) => state.config);
  const connection = useStore(activeStore, (state) => state.connection);
  const timelineItems = useStore(activeStore, (state) => state.items);
  const context = useStore(activeStore, (state) => state.context);
  const sessions = useStore(activeStore, (state) => state.sessions);
  const projects = useStore(activeStore, (state) => state.projects);
  const sessionId = useStore(activeStore, (state) => state.sessionId);
  const changes = useStore(activeStore, (state) => state.changes);
  const filePreview = useStore(activeStore, (state) => state.filePreview);
  const completion = useStore(activeStore, (state) => state.completion);
  const runtime = useStore(activeStore, (state) => state.runtime);
  const modelCatalog = useStore(activeStore, (state) => state.modelCatalog);
  const memoryState = useStore(activeStore, (state) => state.memoryState);
  const skillsState = useStore(activeStore, (state) => state.skillsState);
  const events = useStore(activeStore, (state) => state.events);
  const applyEvent = useStore(activeStore, (state) => state.applyEvent);
  const setConnection = useStore(activeStore, (state) => state.setConnection);
  const clearView = useStore(activeStore, (state) => state.clearView);
  const conversationRef = useRef<HTMLElement>(null);
  const timelineEndRef = useRef<HTMLDivElement>(null);
  const followTimeline = useRef(true);
  const pendingProviderRestart = useRef<{ transactionId?: string } | null>(null);
  const pendingProviderDelete = useRef<string | null>(null);
  const pendingModelDelete = useRef<{ provider: string; model: string } | null>(null);
  const desktopResumeSent = useRef(false);
  const desktopProbeSent = useRef(false);
  const expectedGatewayRestart = useRef(false);

  useEffect(() => {
    if (!transport) return;
    let mounted = true;
    setConnection("connecting");
    const unsubscribe = transport.subscribe(applyEvent);
    const unsubscribeStatus = transport.subscribeStatus((status) => {
      if (!mounted) return;
      if (status === "disconnected" && expectedGatewayRestart.current) {
        setConnection("connecting");
        setConnectionError("");
        return;
      }
      if (status !== "connected") setConnection(status);
      if (status === "connected") {
        expectedGatewayRestart.current = false;
        setConnectionActivity("startup");
        setConnectionError("");
      }
      if (status === "disconnected") setConnectionError("与本地 Agent 运行时的连接已断开");
    });
    void transport.connect().catch((error: unknown) => {
      if (mounted) {
        setConnection("error");
        setConnectionError(error instanceof Error ? error.message : "无法连接本地 Agent 运行时");
      }
    });
    const closeOnPageExit = () => transport.close();
    window.addEventListener("pagehide", closeOnPageExit);
    return () => {
      mounted = false;
      unsubscribe();
      unsubscribeStatus();
      window.removeEventListener("pagehide", closeOnPageExit);
    };
  }, [applyEvent, setConnection, transport]);

  const effectiveBusy = busy || runtimeBusy;
  const effectiveWorkspaceName = runtimeConfig?.workspaceName ?? workspaceName;
  const effectiveWorkspacePath = runtimeConfig?.workspacePath ?? workspacePath;
  const effectiveModel = runtimeConfig?.model ?? modelName;
  const effectivePermissions = runtimeConfig?.permissions ?? permissions;
  const ready = !transport || connection === "connected";
  const activeSessionTitle =
    sessions.find((session) => session.id === sessionId)?.title?.trim() || "新任务";
  const workingState = effectiveBusy
    ? {
        status: progress?.status ?? "executing",
        step: progress?.step ?? 0,
        maxSteps: runtime?.steps?.current ?? 24,
        contextLeft: Math.max(0, Math.min(100, Math.round(100 - (context?.percentUsed ?? 0)))),
      }
    : null;

  useEffect(() => {
    if (!followTimeline.current || !timelineItems.length) return;
    const frame = window.requestAnimationFrame(() => timelineEndRef.current?.scrollIntoView?.());
    return () => window.cancelAnimationFrame(frame);
  }, [timelineItems]);

  useEffect(() => {
    if (!effectiveBusy || !transport) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") transport.request("turn.cancel");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [effectiveBusy, transport]);

  useEffect(() => {
    const event = events.at(-1);
    const pending = pendingProviderRestart.current;
    if (!pending || !event) return;
    if (event.type === "error") {
      pendingProviderRestart.current = null;
      const rollback = pending.transactionId
        ? window.forgeDesktop?.rollbackProviderCredential(pending.transactionId)
        : Promise.resolve(false);
      void rollback?.finally(() => setCommandFeedback(String(event.data.message ?? "模型配置失败")));
      return;
    }
    if (
      event.type !== "command.completed"
      || !["model.provider.upsert", "model.update"].includes(String(event.data.command))
    ) return;
    pendingProviderRestart.current = null;
    const commit = pending.transactionId
      ? window.forgeDesktop?.commitProviderCredential(pending.transactionId)
      : Promise.resolve(true);
    expectedGatewayRestart.current = true;
    setConnectionActivity("model-restart");
    setConnection("connecting");
    setConnectionError("");
    void commit?.then(() => window.forgeDesktop?.restartGateway({
        workspace: effectiveWorkspacePath,
        ...(sessionId ? { sessionId } : {}),
        probeModel: true,
      }),
    ).catch((error: unknown) => {
      expectedGatewayRestart.current = false;
      setConnectionActivity("startup");
      setConnection("error");
      if (pending.transactionId) {
        void window.forgeDesktop?.rollbackProviderCredential(pending.transactionId);
      }
      setCommandFeedback(error instanceof Error ? error.message : "本地运行时重启失败");
    });
  }, [effectiveWorkspacePath, events, sessionId]);

  useEffect(() => {
    const event = events.at(-1);
    const provider = pendingProviderDelete.current;
    if (!event || !provider) return;
    if (event.type === "error") {
      pendingProviderDelete.current = null;
      setCommandFeedback(String(event.data.message ?? "删除模型配置失败"));
      return;
    }
    if (event.type !== "command.completed" || event.data.command !== "model.provider.delete") return;
    pendingProviderDelete.current = null;
    void window.forgeDesktop?.deleteProviderCredential(provider)
      .then(() => setCommandFeedback(`已删除 ${provider} 的模型配置与安全凭据`))
      .catch(() => setCommandFeedback(`已删除 ${provider} 的模型配置；安全凭据清理失败`));
  }, [events]);

  useEffect(() => {
    const event = events.at(-1);
    const pending = pendingModelDelete.current;
    if (!event || !pending) return;
    if (event.type === "error") {
      pendingModelDelete.current = null;
      setCommandFeedback(String(event.data.message ?? "删除模型失败"));
      return;
    }
    if (event.type !== "command.completed" || event.data.command !== "model.delete") return;
    pendingModelDelete.current = null;
    if (event.data.provider_deleted === true) {
      void window.forgeDesktop?.deleteProviderCredential(pending.provider)
        .then(() => setCommandFeedback(`已删除 ${pending.provider} / ${pending.model} 及不再使用的安全凭据`))
        .catch(() => setCommandFeedback(`已删除 ${pending.provider} / ${pending.model}；安全凭据清理失败`));
      return;
    }
    setCommandFeedback(`已删除 ${pending.provider} / ${pending.model}`);
  }, [events]);

  useEffect(() => {
    const event = events.at(-1);
    if (event?.type !== "command.completed" || event.data.command !== "model.probe") return;
    const probe = event.data.probe as { ok?: unknown; message?: unknown } | undefined;
    setDrawerOpen(true);
    setDrawerView("settings");
    setModelSetupOpen(true);
    setCommandFeedback(
      typeof probe?.message === "string"
        ? probe.message
        : probe?.ok === true
          ? "模型连接验证成功"
          : "模型连接验证失败，请检查服务商配置",
    );
  }, [events]);

  useEffect(() => {
    if (!transport || connection !== "connected" || !runtimeConfig || desktopResumeSent.current) return;
    const session = new URLSearchParams(window.location.search).get("resume");
    if (!session || !/^[0-9a-f]{24}$/.test(session)) return;
    desktopResumeSent.current = true;
    transport.request("session.resume", { session_id: session });
    const url = new URL(window.location.href);
    url.searchParams.delete("resume");
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [connection, runtimeConfig, transport]);

  useEffect(() => {
    if (!transport || connection !== "connected" || !runtimeConfig || desktopProbeSent.current) return;
    const query = new URLSearchParams(window.location.search);
    if (query.get("probe") !== "1") return;
    desktopProbeSent.current = true;
    setDrawerOpen(true);
    setDrawerView("settings");
    setModelSetupOpen(true);
    transport.request("model.probe");
    const url = new URL(window.location.href);
    url.searchParams.delete("probe");
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [connection, runtimeConfig, transport]);

  const resolveApproval = (approvalId: string, decision: ApprovalDecision) =>
    transport?.request("approval.resolve", { approval_id: approvalId, decision }) ?? false;

  const reconnect = () => {
    if (!transport) return;
    setConnectionError("");
    void transport.connect().catch((error: unknown) => {
      setConnection("error");
      setConnectionError(error instanceof Error ? error.message : "无法连接本地 Agent 运行时");
    });
  };

  const executeInput = (value: string): boolean => {
    if (!value.startsWith("/")) return transport?.request("turn.start", { task: value }) ?? false;
    const [command, ...parts] = value.trim().split(/\s+/);
    const argument = parts.join(" ");
    setCommandFeedback("");
    if (command === "/help") {
      setHelpOpen(true);
      transport?.request("completion.query", { text: "/", cursor: 1, limit: 100 });
      return true;
    }
    if (command === "/status") {
      transport?.request("runtime.status");
      setDrawerView("run");
      setDrawerOpen(true);
      return true;
    }
    if (command === "/diff") {
      transport?.request("changes.list");
      setDrawerView("changes");
      setDrawerOpen(true);
      return true;
    }
    if (command === "/plan") return transport?.request("plan.get") ?? false;
    if (command === "/new") return transport?.request("session.create") ?? false;
    if (command === "/resume") {
      if (argument) return transport?.request("session.resume", { session_id: argument }) ?? false;
      setRailCollapsed(false);
      setCommandFeedback("请从左侧最近任务中选择要恢复的会话。");
      return true;
    }
    if (command === "/steps") {
      setDrawerView("settings");
      setDrawerOpen(true);
      if (!argument) return transport?.request("steps.get") ?? false;
      if (argument === "reset") return transport?.request("steps.reset") ?? false;
      const valueNumber = Number(argument);
      if (!Number.isInteger(valueNumber) || valueNumber < 12 || valueNumber > 100) {
        setCommandFeedback("Steps 必须是 12–100 的整数，或使用 /steps reset。");
        return true;
      }
      return transport?.request("steps.set", { value: valueNumber }) ?? false;
    }
    if (command === "/permissions") {
      setDrawerView("settings");
      setDrawerOpen(true);
      if (!argument) return transport?.request("permissions.get") ?? false;
      if (!["prompt", "auto", "read-only"].includes(argument)) {
        setCommandFeedback("权限模式只能是 prompt、auto 或 read-only。");
        return true;
      }
      return transport?.request("permissions.set", { mode: argument }) ?? false;
    }
    if (command === "/model") {
      setDrawerView("settings");
      setDrawerOpen(true);
      if (!argument) {
        setModelSetupOpen(false);
        return transport?.request("model.list") ?? false;
      }
      if (argument === "reload") return transport?.request("model.reload") ?? false;
      const modelParts = argument.split(/\s+/);
      const usesProviderSyntax = modelParts[0] === "use";
      if (usesProviderSyntax) modelParts.shift();
      const provider = usesProviderSyntax
        ? modelParts.shift()
        : (modelCatalog?.active?.provider ?? runtime?.model?.provider);
      const modelId = usesProviderSyntax ? (modelParts.join(" ") || undefined) : argument;
      if (!provider) {
        setCommandFeedback("请先打开模型列表，选择服务商与模型。");
        transport?.request("model.list");
        return true;
      }
      return transport?.request("model.select", { provider, ...(modelId ? { model_id: modelId } : {}) }) ?? false;
    }
    if (command === "/memory") {
      setDrawerView("resources");
      setDrawerOpen(true);
      if (!argument || argument === "list") return transport?.request("memory.list") ?? false;
      if (argument === "on" || argument === "off") {
        return transport?.request("memory.toggle", { enabled: argument === "on" }) ?? false;
      }
      if (argument.startsWith("remember ")) {
        return transport?.request("memory.remember", { content: argument.slice(9).trim() }) ?? false;
      }
      if (argument.startsWith("forget ")) {
        return transport?.request("memory.forget", { memory_id: argument.slice(7).trim() }) ?? false;
      }
      if (argument === "clear confirm") return transport?.request("memory.clear", { confirm: true }) ?? false;
      setCommandFeedback("Memory 用法：list、on、off、remember TEXT、forget ID、clear confirm。");
      return true;
    }
    if (command === "/skills") {
      setDrawerView("resources");
      setDrawerOpen(true);
      if (!argument || argument === "list" || argument.startsWith("search ")) {
        return transport?.request("skills.list") ?? false;
      }
      if (argument === "reload") return transport?.request("skills.reload") ?? false;
      const [action, name] = argument.split(/\s+/, 2);
      if ((action === "enable" || action === "disable") && name) {
        return transport?.request("skills.toggle", { name, enabled: action === "enable" }) ?? false;
      }
      setCommandFeedback("Skills 用法：list、search QUERY、enable NAME、disable NAME、reload。");
      return true;
    }
    if (command === "/compact") {
      setDrawerView("context");
      setDrawerOpen(true);
      return transport?.request("context.compact") ?? false;
    }
    if (command === "/raw") {
      if (!argument) setCommandFeedback(`完整工具详情当前${showRaw ? "展开" : "折叠"}。使用 /raw on|off 修改。`);
      else if (argument === "on" || argument === "off") setShowRaw(argument === "on");
      else setCommandFeedback("详情用法：/raw、/raw on 或 /raw off。");
      return true;
    }
    if (command === "/clear") {
      clearView();
      return true;
    }
    if (command === "/exit") {
      window.close();
      return true;
    }
    setCommandFeedback(`${command} 尚未接入桌面管理面板，不会发送给模型。`);
    return true;
  };

  return (
    <div className={`desktop-root${desktop ? " is-desktop" : ""}`}>
      {desktop ? (
        <div className="desktop-titlebar" aria-hidden="true" />
      ) : null}
      <div
        className={`app-shell${drawerOpen ? " has-drawer" : ""}${railCollapsed ? " rail-collapsed" : ""}`}
        style={{ "--inspector-width": `${drawerWidth}px` } as CSSProperties}
      >
      <SessionRail
        productName={productName}
        workspaceName={effectiveWorkspaceName}
        busy={effectiveBusy}
        open={railOpen}
        sessions={sessions}
        projects={projects}
        activeSessionId={sessionId}
        collapsed={railCollapsed}
        addingProject={addingProject}
        projectFeedback={projectFeedback}
        onToggleCollapsed={() => setRailCollapsed((value) => !value)}
        onNewSession={() => {
          if (transport?.request("session.create")) setRailOpen(false);
        }}
        onResumeSession={(nextSessionId) => {
          if (transport?.request("session.resume", { session_id: nextSessionId })) {
            setRailOpen(false);
          }
        }}
        onDeleteSession={(deletedSessionId) => {
          transport?.request("session.delete", { session_id: deletedSessionId });
        }}
        onOpenProject={(projectPath, nextSessionId) => {
          if (effectiveBusy) return;
          expectedGatewayRestart.current = true;
          setConnectionActivity("workspace-restart");
          setConnection("connecting");
          setConnectionError("");
          void window.forgeDesktop?.restartGateway({ workspace: projectPath, sessionId: nextSessionId }).catch((error: unknown) => {
            expectedGatewayRestart.current = false;
            setConnectionActivity("startup");
            setConnection("error");
            setConnectionError(error instanceof Error ? error.message : "无法打开项目");
            setCommandFeedback(error instanceof Error ? error.message : "无法打开项目");
          });
        }}
        onAddProject={() => {
          if (effectiveBusy || addingProject) return;
          if (!window.forgeDesktop) {
            setProjectFeedback("添加项目仅在桌面应用中可用");
            return;
          }
          setAddingProject(true);
          setProjectFeedback("正在打开目录选择器…");
          void window.forgeDesktop.selectWorkspace().then(async (projectPath) => {
            if (!projectPath) {
              setProjectFeedback("");
              return;
            }
            setProjectFeedback("正在打开所选项目…");
            expectedGatewayRestart.current = true;
            setConnectionActivity("workspace-restart");
            setConnection("connecting");
            setConnectionError("");
            await window.forgeDesktop?.restartGateway({ workspace: projectPath });
          }).catch((error: unknown) => {
            expectedGatewayRestart.current = false;
            setConnectionActivity("startup");
            setConnection("error");
            setConnectionError(error instanceof Error ? error.message : "无法添加项目");
            setProjectFeedback(error instanceof Error ? error.message : "无法添加项目");
          }).finally(() => {
            setAddingProject(false);
          });
        }}
        onRemoveProject={(projectPath) => {
          transport?.request("project.remove", { path: projectPath });
        }}
      />
      {railOpen && (
        <button
          type="button"
          className="rail-backdrop"
          aria-label="关闭会话栏"
          onClick={() => setRailOpen(false)}
        />
      )}
      <section className="conversation-column">
        <WorkspaceHeader
          taskTitle={activeSessionTitle}
          projectName={effectiveWorkspaceName}
          onToggleRail={() => setRailOpen((value) => !value)}
        />
        <ConnectionTransition
          state={connection}
          ready={ready}
          error={connectionError}
          activity={connectionActivity}
          onRetry={reconnect}
          onOpenSettings={() => {
            setConnectionError("");
            setDrawerView("settings");
            setDrawerOpen(true);
            setModelSetupOpen(true);
          }}
        />
        <main
          className="conversation"
          aria-label="Agent 会话"
          ref={conversationRef}
          onScroll={() => {
            const node = conversationRef.current;
            if (!node) return;
            followTimeline.current = node.scrollHeight - node.scrollTop - node.clientHeight < 120;
          }}
        >
          {helpOpen ? (
            <CommandGuide
              commands={completion?.text === "/" ? completion.items : []}
              onClose={() => setHelpOpen(false)}
              onChoose={(command) => {
                setHelpOpen(false);
                executeInput(command);
              }}
            />
          ) : timelineItems.length || effectiveBusy ? (
            <Timeline
              items={timelineItems}
              working={workingState}
              onApproval={resolveApproval}
              approvalAvailable={ready}
              showRaw={showRaw}
            />
          ) : (
            <div className="empty-conversation">
              <span className="empty-kicker">Local coding agent</span>
              <h1>今天想做点什么？</h1>
              <p>
                描述您想完成的修改。Agent 会读取项目、提出计划，并在必要时请求您的审批。
              </p>
              <div className="capability-row" aria-label="核心能力">
                <span>理解项目</span>
                <i />
                <span>安全审批</span>
                <i />
                <span>验证改动</span>
              </div>
            </div>
          )}
          {commandFeedback ? (
            <div className="command-feedback" role="status">
              <span>{commandFeedback}</span>
              <button type="button" onClick={() => setCommandFeedback("")}>关闭</button>
            </div>
          ) : null}
          <div className="timeline-anchor" ref={timelineEndRef} />
        </main>
        <Composer
          busy={effectiveBusy}
          ready={ready}
          modelName={effectiveModel}
          permissions={effectivePermissions}
          contextPercent={context?.percentUsed}
          completion={completion}
          onCompletionQuery={(text, cursor) => transport?.request("completion.query", { text, cursor, limit: 40 })}
          onOpenModel={() => {
            setDrawerView("settings");
            setDrawerOpen(true);
            setModelSetupOpen(false);
            transport?.request("model.list");
          }}
          onOpenPermissions={() => {
            setDrawerView("settings");
            setDrawerOpen(true);
            transport?.request("runtime.status");
          }}
          onOpenContext={() => {
            setDrawerView("context");
            setDrawerOpen(true);
            transport?.request("context.get");
          }}
          onOpenInspector={() => {
            if (drawerView === "changes") transport?.request("changes.list");
            setDrawerOpen(true);
          }}
          onSend={executeInput}
          onStop={() => transport?.request("turn.cancel")}
        />
      </section>
      {drawerOpen && (
        <ContextDrawer
          width={drawerWidth}
          onWidthChange={(value) => {
            setDrawerWidth(value);
            window.localStorage.setItem("forge.inspector.width", String(value));
          }}
          changes={changes}
          timelineItems={timelineItems}
          filePreview={filePreview}
          onPreview={(path) => {
            transport?.request("file.preview", { path });
          }}
          onReviewChange={(changeId, decision) => {
            transport?.request("change.review", { change_id: changeId, decision });
          }}
          onReviewAll={(decision) => {
            transport?.request("changes.review", { decision });
          }}
          key={drawerView}
          initialTab={drawerView}
          openModelManager={modelSetupOpen}
          onTabChange={setDrawerView}
          busy={effectiveBusy}
          modelName={effectiveModel}
          permissions={effectivePermissions}
          contextPercent={context?.percentUsed}
          runtime={runtime}
          modelCatalog={modelCatalog}
          memoryState={memoryState}
          skillsState={skillsState}
          onRuntimeRefresh={() => transport?.request("runtime.status")}
          onModelList={() => transport?.request("model.list")}
          onModelSelect={(provider, modelId) => transport?.request("model.select", { provider, model_id: modelId })}
          onModelReload={() => transport?.request("model.reload")}
          onModelProviderConfigure={async (input) => {
            if (!window.forgeDesktop) throw new Error("添加服务商仅在桌面应用中可用");
            const saved = input.preserveCredential
              ? null
              : await window.forgeDesktop.saveProviderCredential({
                  provider: input.provider,
                  apiKey: input.apiKey,
                });
            const accepted = transport?.request("model.provider.upsert", {
              provider: input.provider,
              base_url: input.baseUrl,
              model: input.model,
              compatibility: input.compatibility,
            });
            if (!accepted) {
              if (saved) await window.forgeDesktop.rollbackProviderCredential(saved.transactionId);
              throw new Error("本地运行时未连接，模型元数据尚未保存");
            }
            pendingProviderRestart.current = saved
              ? { transactionId: saved.transactionId }
              : {};
            return saved ?? { persisted: true, backend: "existing" };
          }}
          onModelProviderDelete={(provider) => {
            const accepted = transport?.request("model.provider.delete", { provider, confirm: true });
            if (!accepted) {
              setCommandFeedback("本地运行时未连接，模型配置尚未删除");
              return;
            }
            pendingProviderDelete.current = provider;
          }}
          onModelUpdate={(input: ModelUpdateInput) => {
            const accepted = transport?.request("model.update", {
              provider: input.provider,
              original_model: input.originalModel,
              model: input.model,
              base_url: input.baseUrl,
              compatibility: input.compatibility,
            });
            if (!accepted) throw new Error("本地运行时未连接，模型修改尚未保存");
            pendingProviderRestart.current = {};
          }}
          onModelDelete={(provider, model) => {
            const accepted = transport?.request("model.delete", { provider, model, confirm: true });
            if (!accepted) throw new Error("本地运行时未连接，模型尚未删除");
            pendingModelDelete.current = { provider, model };
          }}
          onPermissionChange={(mode) => transport?.request("permissions.set", { mode })}
          onStepsChange={(value) => transport?.request("steps.set", { value }) ?? false}
          onStepsReset={() => transport?.request("steps.reset") ?? false}
          onVerificationChange={(commands) =>
            transport?.request("verification.set", { commands }) ?? false
          }
          onMemoryList={() => transport?.request("memory.list")}
          onMemoryToggle={(enabled) => transport?.request("memory.toggle", { enabled })}
          onRemember={(content) => transport?.request("memory.remember", { content })}
          onForget={(memoryId) => transport?.request("memory.forget", { memory_id: memoryId })}
          onMemoryClear={() => transport?.request("memory.clear", { confirm: true })}
          onSkillsList={() => transport?.request("skills.list")}
          onSkillToggle={(name, enabled) => transport?.request("skills.toggle", { name, enabled })}
          onSkillsReload={() => transport?.request("skills.reload")}
          onSkillDraft={(requirement, template) =>
            transport?.request("skills.draft", { requirement, template }) ?? false
          }
          onSkillCreate={(input) => transport?.request("skills.create", input) ?? false}
          onCompact={() => transport?.request("context.compact")}
          onClose={() => {
            setDrawerOpen(false);
            setModelSetupOpen(false);
          }}
        />
      )}
      </div>
    </div>
  );
}
