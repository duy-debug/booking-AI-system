"use client";

import { useEffect, useRef, useState } from "react";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { MessageComposer } from "@/components/chat/MessageComposer";
import { MessageItem } from "@/components/chat/MessageItem";
import { BotIcon } from "@/components/common/Icons";
import { useBookingChat } from "@/hooks/use-booking-chat";

export function ChatApp() {
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
    const frame = window.requestAnimationFrame(() => {
      setDark(localStorage.getItem("booking-chat-theme") === "dark");
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("booking-chat-theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) return;
    const frame = window.requestAnimationFrame(() => {
      const container = messageScrollRef.current;
      if (container) container.scrollTop = container.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, isSending, streamingStarted]);

  useEffect(() => {
    if (!isSending) {
      document.querySelector<HTMLTextAreaElement>(".composer textarea")?.focus();
    }
  }, [isSending]);

  function submit() {
    const value = input.trim();
    if (!value || isSending) return;
    setInput("");
    void sendMessage(value);
  }

  function resetChat() {
    resetConversation();
    setInput("");
    shouldAutoScrollRef.current = true;
  }

  return (
    <main className="messenger-shell">
      <section className="chat-panel">
        <ChatHeader
          loading={isSending}
          streaming={streamingStarted}
          dark={dark}
          onToggleTheme={() => setDark((value) => !value)}
          onNewChat={resetChat}
        />

        <div
          ref={messageScrollRef}
          className="message-scroll"
          aria-live="polite"
          aria-busy={isSending}
          onScroll={(event) => {
            const element = event.currentTarget;
            shouldAutoScrollRef.current =
              element.scrollHeight - element.scrollTop - element.clientHeight < 120;
          }}
        >
          <div className="conversation-date"><span>Hôm nay</span></div>
          <div className="message-stream">
            {messages.map((message, index) => (
              <MessageItem
                key={message.id}
                message={message}
                latest={index === messages.length - 1}
                loading={isSending}
                streaming={isSending && streamingStarted}
                onQuickReply={(reply) => void sendMessage(reply)}
              />
            ))}

            {isSending && !streamingStarted && (
              <div className="message-row assistant" role="status">
                <span className="message-avatar"><BotIcon /></span>
                <div>
                  <div className="typing"><i /><i /><i /></div>
                  <small className="typing-label">Kori đang suy nghĩ</small>
                </div>
              </div>
            )}

            {error && (
              <div className="error-banner" role="alert">
                <span><strong>Không gửi được tin nhắn</strong>{error}</span>
                {canRetry && (
                  <button disabled={isSending} onClick={retryLastMessage}>Thử lại</button>
                )}
              </div>
            )}
          </div>
          <div className="scroll-anchor" />
        </div>

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
