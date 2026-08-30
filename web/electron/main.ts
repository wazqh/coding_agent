import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { app, BrowserWindow, dialog, ipcMain, safeStorage, shell } from "electron";

import {
  CredentialStore,
  providerCredentialName,
  resolveProviderCredential,
} from "./credentialStore.js";
import { CredentialTransactionManager } from "./credentialTransactions.js";
import { migrateLegacyCredentials } from "./credentialMigration.js";
import {
  GatewayProcess,
  GatewayTrustRequiredError,
  type ProjectTrustChoice,
} from "./gatewayProcess.js";
import { resolvePreloadPath } from "./preloadPath.js";
import { buildGatewayEnvironment } from "./pythonEnvironment.js";
import { PythonCredentialBridge } from "./pythonCredentialBridge.js";
import { projectTrustChoice } from "./projectTrust.js";
import type { DesktopRuntimeInfo, ProviderCredentialInput, RestartGatewayInput } from "./types.js";
import { installWindowPolicy, isExternalHttpUrl } from "./windowPolicy.js";
import { resolveConfiguredWorkspace } from "./workspaceConfig.js";

const currentDirectory = path.dirname(fileURLToPath(import.meta.url));
const preloadPath = resolvePreloadPath(currentDirectory);
const gateway = new GatewayProcess();

let mainWindow: BrowserWindow | null = null;
let quitting = false;
let currentWorkspace = "";
let disposeWindowPolicy: (() => void) | null = null;
let credentialStore: CredentialStore;
let credentialTransactions: CredentialTransactionManager;
let sharedCredentials: PythonCredentialBridge;

function credentialTransactionId(value: unknown): string {
  if (typeof value !== "string" || value.length < 1 || value.length > 128) {
    throw new Error("Invalid credential transaction");
  }
  return value;
}

function configuredWorkspace(): string {
  return resolveConfiguredWorkspace(process.argv, process.env, process.cwd());
}

function configuredPython(): string {
  return process.env.FORGE_PYTHON?.trim() || (process.platform === "win32" ? "python" : "python3");
}

async function configuredPythonEnvironment(): Promise<Record<string, string>> {
  return buildGatewayEnvironment({
    appPath: app.getAppPath(),
    inheritedPythonPath: process.env.PYTHONPATH,
    sourceExists: async (candidate) => {
      try {
        return (await fs.stat(candidate)).isDirectory();
      } catch {
        return false;
      }
    },
  });
}

async function confirmExternal(url: string): Promise<boolean> {
  if (!isExternalHttpUrl(url) || mainWindow === null) return false;
  const result = await dialog.showMessageBox(mainWindow, {
    type: "question",
    title: "打开外部链接",
    message: "此链接将使用系统浏览器打开。",
    detail: url,
    buttons: ["取消", "继续"],
    defaultId: 0,
    cancelId: 0,
    noLink: true,
  });
  if (result.response !== 1) return false;
  await shell.openExternal(url);
  return true;
}

async function requestProjectTrust(workspace: string): Promise<ProjectTrustChoice> {
  if (mainWindow === null) return "ignore";
  const result = await dialog.showMessageBox(mainWindow, {
    type: "question",
    title: "项目资源信任",
    message: `是否加载 ${path.basename(workspace)} 的项目资源？`,
    detail:
      "Forge 发现了 AGENTS.md、coding-agent.toml 或仓库 Skills。仅在您信任此项目后，Agent 才会读取并应用这些资源。",
    buttons: ["忽略项目资源", "仅本次信任", "始终信任"],
    defaultId: 0,
    cancelId: 0,
    noLink: true,
  });
  return projectTrustChoice(result.response);
}

async function startGateway(
  workspace: string,
  sessionId?: string,
  initialTrust?: ProjectTrustChoice,
): Promise<void> {
  if (mainWindow === null) throw new Error("Desktop window is unavailable");
  const developmentEnvironment = await configuredPythonEnvironment();
  const legacyCredentials = await credentialStore.environment();
  const fallbackCredentials = await migrateLegacyCredentials(
    legacyCredentials,
    sharedCredentials,
    (name) => credentialStore.delete(name),
  );
  const environment = { ...fallbackCredentials, ...developmentEnvironment };
  let trustMode = initialTrust;
  let ready;
  try {
    ready = await gateway.start({
      pythonExecutable: configuredPython(),
      workspace,
      environment,
      ...(trustMode ? { trustMode } : {}),
    });
  } catch (error) {
    if (!(error instanceof GatewayTrustRequiredError) || trustMode) throw error;
    await gateway.stop();
    if (path.resolve(error.workspace) !== path.resolve(workspace)) {
      throw new Error("Desktop trust challenge does not match the requested workspace");
    }
    trustMode = await requestProjectTrust(workspace);
    ready = await gateway.start({
      pythonExecutable: configuredPython(),
      workspace,
      environment,
      trustMode,
    });
  }
  currentWorkspace = workspace;
  disposeWindowPolicy?.();
  disposeWindowPolicy = installWindowPolicy(mainWindow.webContents, ready.origin, confirmExternal);
  const query = new URLSearchParams({ desktop: "1" });
  if (sessionId) query.set("resume", sessionId);
  await mainWindow.loadURL(`${ready.origin}/?${query}#capability=${encodeURIComponent(ready.capability)}`);
}

async function restartGateway(workspace: string, sessionId?: string): Promise<void> {
  const resolved = path.resolve(workspace);
  const stat = await fs.stat(resolved);
  if (!stat.isDirectory()) throw new Error("Workspace must be a directory");
  await gateway.stop();
  await startGateway(resolved, sessionId);
}

function installIpc(window: BrowserWindow): void {
  const fromWindow = (event: Electron.IpcMainInvokeEvent): boolean => event.sender === window.webContents;
  ipcMain.handle("desktop:runtime-info", (): DesktopRuntimeInfo => ({
    platform: process.platform,
    gatewayState: gateway.state,
  }));
  ipcMain.handle("desktop:select-workspace", async (event) => {
    if (!fromWindow(event)) return null;
    const result = await dialog.showOpenDialog(window, {
      title: "选择工作区",
      properties: ["openDirectory"],
    });
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });
  ipcMain.handle("desktop:save-provider-credential", async (event, value: unknown) => {
    if (!fromWindow(event) || typeof value !== "object" || value === null) {
      throw new Error("Invalid credential request");
    }
    const input = value as Partial<ProviderCredentialInput>;
    if (typeof input.provider !== "string" || typeof input.apiKey !== "string") {
      throw new Error("Invalid credential request");
    }
    const credential = resolveProviderCredential(input.provider, input.apiKey);
    return credentialTransactions.stage(providerCredentialName(input.provider), credential);
  });
  ipcMain.handle("desktop:commit-provider-credential", async (event, value: unknown) => {
    if (!fromWindow(event)) throw new Error("Invalid credential request");
    return credentialTransactions.commit(credentialTransactionId(value));
  });
  ipcMain.handle("desktop:rollback-provider-credential", async (event, value: unknown) => {
    if (!fromWindow(event)) throw new Error("Invalid credential request");
    return credentialTransactions.rollback(credentialTransactionId(value));
  });
  ipcMain.handle("desktop:restart-gateway", async (event, value: unknown) => {
    if (!fromWindow(event) || typeof value !== "object" || value === null) {
      throw new Error("Invalid restart request");
    }
    const input = value as RestartGatewayInput;
    const workspace = input.workspace;
    if (workspace !== undefined && typeof workspace !== "string") {
      throw new Error("Invalid workspace path");
    }
    if (input.sessionId !== undefined && !/^[0-9a-f]{24}$/.test(input.sessionId)) {
      throw new Error("Invalid session ID");
    }
    await restartGateway(workspace?.trim() || currentWorkspace, input.sessionId);
  });
  ipcMain.handle("desktop:open-external", (event, url: unknown) =>
    fromWindow(event) && typeof url === "string" ? confirmExternal(url) : false,
  );
  ipcMain.on("desktop:window", (event, action: unknown) => {
    if (event.sender !== window.webContents) return;
    if (action === "minimize") window.minimize();
    else if (action === "toggle-maximize") {
      if (window.isMaximized()) window.unmaximize();
      else window.maximize();
    } else if (action === "close") window.close();
  });
}

async function createMainWindow(): Promise<void> {
  credentialStore = new CredentialStore({
    storePath: path.join(app.getPath("userData"), "provider-credentials.json"),
    encryption: safeStorage,
    platform: process.platform,
  });
  const pythonEnvironment = await configuredPythonEnvironment();
  sharedCredentials = new PythonCredentialBridge(configuredPython(), {
    ...process.env,
    ...pythonEnvironment,
  });
  credentialTransactions = new CredentialTransactionManager(
    credentialStore,
    undefined,
    sharedCredentials,
  );
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    backgroundColor: "#f7f9fc",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#eef2f7",
      symbolColor: "#5f6670",
      height: 38,
    },
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  });
  mainWindow = window;
  installIpc(window);
  window.once("ready-to-show", () => window.show());
  window.on("closed", () => {
    if (mainWindow === window) mainWindow = null;
  });
  await startGateway(configuredWorkspace());
}

app.on("before-quit", (event) => {
  if (quitting) return;
  event.preventDefault();
  void gateway.stop().finally(() => {
    quitting = true;
    app.quit();
  });
});

app.on("window-all-closed", () => app.quit());

void app.whenReady().then(createMainWindow).catch(async (error: unknown) => {
  await gateway.stop();
  const message = error instanceof Error ? error.message : "Unknown desktop startup error";
  dialog.showErrorBox("桌面应用无法启动", message);
  quitting = true;
  app.exit(2);
});
