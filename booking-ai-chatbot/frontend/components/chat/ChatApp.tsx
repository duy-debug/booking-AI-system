"use client";

import { useEffect, useRef, useState } from "react";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { MessageComposer } from "@/components/chat/MessageComposer";
import { MessageList } from "@/components/chat/MessageList";
import { useBookingChat } from "@/hooks/use-booking-chat";

interface ChatAppProps {
  mode?: "page" | "widget";
  onClose?: () => void;
}

// Component vỏ của chatbot, nối hook hội thoại với header, message list và input composer.
export function ChatApp({ mode = "page", onClose }: ChatAppProps) {
  const {
    messages,
    conversationId,
    isSending,
    streamingStarted,
    error,
    canRetry,
    sendMessage,
    retryLastMessage,
    resetConversation,
    cancelCurrentRequest,
  } = useBookingChat();
  const [input, setInput] = useState("");
  const [dark, setDark] = useState(false);
  const messageScrollRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);

  useEffect(() => {
    // Đọc theme phía client sau mount để tránh mismatch giữa SSR và localStorage.
    const frame = window.requestAnimationFrame(() => {
      setDark(localStorage.getItem("booking-chat-theme") === "dark");
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    // Đồng bộ theme lên document để CSS token dùng chung cho toàn popup chat.
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("booking-chat-theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    // Chỉ tự cuộn xuống cuối khi người dùng vẫn đang ở gần cuối conversation.
    if (!shouldAutoScrollRef.current) return;
    const frame = window.requestAnimationFrame(() => {
      const container = messageScrollRef.current;
      if (container) container.scrollTop = container.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, isSending, streamingStarted]);

  useEffect(() => {
    // Trả focus về textarea sau khi chatbot xử lý xong để người dùng tiếp tục nhập nhanh.
    if (!isSending) {
      document.querySelector<HTMLTextAreaElement>(".composer textarea")?.focus();
    }
  }, [isSending]);

  // Gửi nội dung hiện tại qua hook chat và xóa input sau khi submit hợp lệ.
  function submit() {
    const value = input.trim();
    if (!value || isSending) return;
    setInput("");
    void sendMessage(value);
  }

  // Tạo conversation mới từ UI nhưng vẫn giữ trạng thái popup hiện tại.
  function resetChat() {
    resetConversation();
    setInput("");
    shouldAutoScrollRef.current = true;
  }

  return (
    <main className={`messenger-shell ${mode === "widget" ? "widget-mode" : "page-mode"}`}>
      <section className="chat-panel">
        <ChatHeader
          loading={isSending}
          streaming={streamingStarted}
          dark={dark}
          onToggleTheme={() => setDark((value) => !value)}
          onNewChat={resetChat}
          onClose={onClose}
          showThemeToggle={mode === "page"}
        />

        <MessageList
          messages={messages}
          loading={isSending}
          streamingStarted={streamingStarted}
          error={error}
          canRetry={canRetry}
          scrollRef={messageScrollRef}
          onRetry={retryLastMessage}
          onScrollNearBottomChange={(nearBottom) => {
            shouldAutoScrollRef.current = nearBottom;
          }}
        />

        {conversationId && (
          <MessageComposer
            value={input}
            loading={isSending}
            onChange={setInput}
            onSubmit={submit}
            onStop={cancelCurrentRequest}
          />
        )}
      </section>
    </main>
  );
}
