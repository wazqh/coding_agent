import { useLayoutEffect, useState } from "react";

export interface ConversationPaneBounds {
  left: number;
  top: number;
  bottom: number;
}

/** Keep inspector-owned preview panes inside the central run surface. */
export function useConversationPaneBounds(): ConversationPaneBounds {
  const [bounds, setBounds] = useState<ConversationPaneBounds>({ left: 16, top: 16, bottom: 16 });

  useLayoutEffect(() => {
    const conversation = document.querySelector<HTMLElement>(".conversation")
      ?? document.querySelector<HTMLElement>(".conversation-column");
    if (!conversation) return undefined;

    const updateBounds = () => {
      const rect = conversation.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      setBounds({
        left: Math.max(12, Math.round(rect.left) + 12),
        top: Math.max(12, Math.round(rect.top) + 12),
        bottom: Math.max(12, Math.round(window.innerHeight - rect.bottom) + 12),
      });
    };
    updateBounds();
    window.addEventListener("resize", updateBounds);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updateBounds);
    observer?.observe(conversation);
    return () => {
      window.removeEventListener("resize", updateBounds);
      observer?.disconnect();
    };
  }, []);

  return bounds;
}
