"use client";

import { useEffect, useState } from "react";
import { ChatApp } from "@/components/chat/ChatApp";
import { BotIcon } from "@/components/common/Icons";
import { OPEN_CHAT_EVENT } from "@/components/landing/ChatOpenButton";

export function ChatWidget() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const openWidget = () => setOpen(true);
    window.addEventListener(OPEN_CHAT_EVENT, openWidget);
    return () => window.removeEventListener(OPEN_CHAT_EVENT, openWidget);
  }, []);

  if (open) {
    return (
      <aside className="chat-widget open" aria-label="Trợ lý AI Kori">
        <div className="chat-widget-window">
          <ChatApp mode="widget" onClose={() => setOpen(false)} />
        </div>
      </aside>
    );
  }

  return (
    <aside className="chat-widget" aria-label="Trợ lý AI Kori">
      <button
        className="chat-widget-button"
        type="button"
        aria-label="Mở trợ lý AI Kori"
        onClick={() => setOpen(true)}
      >
        <BotIcon />
      </button>
    </aside>
  );
}
