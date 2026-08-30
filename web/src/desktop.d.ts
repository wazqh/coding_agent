import type { ForgeDesktopBridge } from "../electron/types";

declare global {
  interface Window {
    forgeDesktop?: ForgeDesktopBridge;
  }
}

export {};
