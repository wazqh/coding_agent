import { contextBridge, ipcRenderer } from "electron";

import type {
  DesktopRuntimeInfo,
  ForgeDesktopBridge,
  ProviderCredentialCopyInput,
  ProviderCredentialInput,
} from "./types.js";

const bridge: ForgeDesktopBridge = Object.freeze({
  runtimeInfo: () => ipcRenderer.invoke("desktop:runtime-info") as Promise<DesktopRuntimeInfo>,
  selectWorkspace: () => ipcRenderer.invoke("desktop:select-workspace") as Promise<string | null>,
  saveProviderCredential: (input: ProviderCredentialInput) =>
    ipcRenderer.invoke("desktop:save-provider-credential", input) as ReturnType<
      ForgeDesktopBridge["saveProviderCredential"]
    >,
  copyProviderCredential: (input: ProviderCredentialCopyInput) =>
    ipcRenderer.invoke("desktop:copy-provider-credential", input) as ReturnType<
      ForgeDesktopBridge["copyProviderCredential"]
    >,
  commitProviderCredential: (transactionId: string) =>
    ipcRenderer.invoke("desktop:commit-provider-credential", transactionId) as Promise<boolean>,
  rollbackProviderCredential: (transactionId: string) =>
    ipcRenderer.invoke("desktop:rollback-provider-credential", transactionId) as Promise<boolean>,
  deleteProviderCredential: (provider: string) =>
    ipcRenderer.invoke("desktop:delete-provider-credential", provider) as Promise<void>,
  restartGateway: (input = {}) =>
    ipcRenderer.invoke("desktop:restart-gateway", input) as Promise<void>,
  openExternal: (url: string) => ipcRenderer.invoke("desktop:open-external", url) as Promise<boolean>,
  minimize: () => ipcRenderer.send("desktop:window", "minimize"),
  toggleMaximize: () => ipcRenderer.send("desktop:window", "toggle-maximize"),
  close: () => ipcRenderer.send("desktop:window", "close"),
});

contextBridge.exposeInMainWorld("forgeDesktop", bridge);
