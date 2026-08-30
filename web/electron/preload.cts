import { contextBridge, ipcRenderer } from "electron";

import type { DesktopRuntimeInfo, ForgeDesktopBridge, ProviderCredentialInput } from "./types.js";

const bridge: ForgeDesktopBridge = Object.freeze({
  runtimeInfo: () => ipcRenderer.invoke("desktop:runtime-info") as Promise<DesktopRuntimeInfo>,
  selectWorkspace: () => ipcRenderer.invoke("desktop:select-workspace") as Promise<string | null>,
  saveProviderCredential: (input: ProviderCredentialInput) =>
    ipcRenderer.invoke("desktop:save-provider-credential", input) as ReturnType<
      ForgeDesktopBridge["saveProviderCredential"]
    >,
  commitProviderCredential: (transactionId: string) =>
    ipcRenderer.invoke("desktop:commit-provider-credential", transactionId) as Promise<boolean>,
  rollbackProviderCredential: (transactionId: string) =>
    ipcRenderer.invoke("desktop:rollback-provider-credential", transactionId) as Promise<boolean>,
  restartGateway: (input = {}) =>
    ipcRenderer.invoke("desktop:restart-gateway", input) as Promise<void>,
  openExternal: (url: string) => ipcRenderer.invoke("desktop:open-external", url) as Promise<boolean>,
  minimize: () => ipcRenderer.send("desktop:window", "minimize"),
  toggleMaximize: () => ipcRenderer.send("desktop:window", "toggle-maximize"),
  close: () => ipcRenderer.send("desktop:window", "close"),
});

contextBridge.exposeInMainWorld("forgeDesktop", bridge);
