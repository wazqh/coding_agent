export function isAllowedNavigation(target: string, gatewayOrigin: string): boolean {
  try {
    const targetUrl = new URL(target);
    const originUrl = new URL(gatewayOrigin);
    return targetUrl.origin === originUrl.origin;
  } catch {
    return false;
  }
}

export function isExternalHttpUrl(target: string): boolean {
  try {
    const protocol = new URL(target).protocol;
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

export function installWindowPolicy(
  webContents: WebContents,
  gatewayOrigin: string,
  confirmExternal: (url: string) => Promise<boolean>,
): () => void {
  webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => {
    callback(false);
  });
  webContents.setWindowOpenHandler(({ url }) => {
    if (isExternalHttpUrl(url)) void confirmExternal(url);
    return { action: "deny" };
  });
  const onNavigate = (event: Electron.Event, url: string): void => {
    if (isAllowedNavigation(url, gatewayOrigin)) return;
    event.preventDefault();
    if (isExternalHttpUrl(url)) void confirmExternal(url);
  };
  webContents.on("will-navigate", onNavigate);
  return () => webContents.removeListener("will-navigate", onNavigate);
}
import type { WebContents } from "electron";
