import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { WebSocketTransport } from "./protocol/websocketTransport";

const productName =
  document.querySelector<HTMLMetaElement>('meta[name="forge-product-name"]')?.content ?? "";
const transport = new WebSocketTransport();
const desktop = new URLSearchParams(window.location.search).get("desktop") === "1";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App
      productName={productName}
      workspaceName="当前项目"
      workspacePath="正在连接本地运行时…"
      modelName="未连接"
      permissions="prompt"
      transport={transport}
      desktop={desktop}
    />
  </StrictMode>,
);
