"use client";

import { useEffect, useState } from "react";
import { ChatApp } from "@/components/chat/ChatApp";
import { BotIcon } from "@/components/common/Icons";
import { OPEN_CHAT_EVENT } from "@/components/landing/ChatOpenButton";

// Điều khiển popup chatbot nổi trên landing page mà không thay đổi logic hội thoại bên trong.
export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);

  useEffect(() => {
    // Cho các CTA trên landing page mở cùng một popup chat thông qua custom event.
    const openWidget = () => {
      setHasOpened(true);
      setOpen(true);
    };
    window.addEventListener(OPEN_CHAT_EVENT, openWidget);
    return () => window.removeEventListener(OPEN_CHAT_EVENT, openWidget);
  }, []);

  // Mở popup từ floating button và chỉ mount ChatApp sau lần mở đầu tiên để giữ chi phí render thấp.
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
