"use client";

import { useEffect, useState } from "react";
import { ChatApp } from "@/components/chat/ChatApp";
import { BotIcon } from "@/components/common/Icons";
import { OPEN_CHAT_EVENT } from "@/components/landing/ChatOpenButton";

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);

  useEffect(() => {
    const openWidget = () => {
      setHasOpened(true);
      setOpen(true);
    };
    window.addEventListener(OPEN_CHAT_EVENT, openWidget);
    return () => window.removeEventListener(OPEN_CHAT_EVENT, openWidget);
  }, []);

  function openChat() {
    setHasOpened(true);
    setOpen(true);
  }

  return (
    <aside className={`chat-widget${open ? " open" : ""}`} aria-label="Trợ lý AI Kori">
      {hasOpened && (
        <div className="chat-widget-window" hidden={!open}>
          <ChatApp mode="widget" onClose={() => setOpen(false)} />
        </div>
      )}

      {!open && (
        <button
          className="chat-widget-button"
          type="button"
          aria-label="Mở trợ lý AI Kori"
          onClick={openChat}
        >
          <BotIcon />
        </button>
      )}
    </aside>
  );
}
