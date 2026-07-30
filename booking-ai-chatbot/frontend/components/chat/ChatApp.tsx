"use client";

import { useEffect, useRef, useState } from "react";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { MessageComposer } from "@/components/chat/MessageComposer";
import { MessageItem } from "@/components/chat/MessageItem";
import { BotIcon } from "@/components/common/Icons";
import { ChatApiError, streamChat } from "@/services/chat-api";
import { loadConversationId, saveConversationSession } from "@/services/chat-session";
import type { ChatMessage } from "@/types/chat";

const WELCOME_TEXT = "Xin chào! Mình là Kori, trợ lý wellness của Komorebi. Mình có thể giúp bạn đặt lịch, tra cứu, đổi hoặc hủy lịch hẹn. Hôm nay bạn cần mình hỗ trợ gì?";

const makeConversationId = () => crypto.randomUUID();
const makeWelcome = (): ChatMessage => ({
  id: crypto.randomUUID(),
  role: "assistant",
  text: WELCOME_TEXT,
  createdAt: Date.now(),
});

export function ChatApp() {
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingStarted, setStreamingStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastPrompt, setLastPrompt] = useState("");
  const [dark, setDark] = useState(false);
  const messageScrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const storedConversation = loadConversationId(localStorage);
      localStorage.removeItem("booking-chat-conversation");
      const storedTheme = localStorage.getItem("booking-chat-theme");
      const nextConversation = storedConversation || makeConversationId();
      setConversationId(nextConversation);
      setDark(storedTheme === "dark");
      setMessages([makeWelcome()]);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("booking-chat-theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    if (conversationId) saveConversationSession(localStorage, conversationId);
  }, [conversationId]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const container = messageScrollRef.current;
      if (container) container.scrollTop = container.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [messages, loading, streamingStarted]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function interact(userText: string) {
    if (!conversationId || inFlightRef.current) return;
    inFlightRef.current = true;
    saveConversationSession(localStorage, conversationId);
    const assistantMessageId = crypto.randomUUID();
    const controller = new AbortController();
    abortRef.current = controller;
    setLastPrompt(userText);
    setError(null);
    setStreamingStarted(false);
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: userText, createdAt: Date.now() },
      { id: assistantMessageId, role: "assistant", text: "", createdAt: Date.now() },
    ]);
    setLoading(true);

    try {
      await streamChat(
        {
          conversationId,
          query: userText,
          signal: controller.signal,
        },
        {
          onToken: (delta) => {
            setStreamingStarted(true);
            setMessages((current) => current.map((message) => (
              message.id === assistantMessageId ? { ...message, text: message.text + delta } : message
            )));
          },
          onDone: (response) => {
            setMessages((current) => current.map((message) => (
              message.id === assistantMessageId ? { ...message, text: response.answer, response } : message
            )));
          },
        },
      );
    } catch (cause) {
      if (controller.signal.aborted) {
        setMessages((current) => current.map((message) => (
          message.id === assistantMessageId && !message.text
            ? { ...message, text: "Đã dừng tạo câu trả lời." }
            : message
        )));
      } else {
        setMessages((current) => current.filter((message) => (
          message.id !== assistantMessageId || message.text.length > 0
        )));
        setError(cause instanceof ChatApiError
          ? cause.problem.detail
          : "Không thể kết nối đến trợ lý. Vui lòng thử lại.");
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        inFlightRef.current = false;
        setLoading(false);
      }
    }
  }

  function submit() {
    const value = input.trim();
    if (!value || loading) return;
    setInput("");
    void interact(value);
  }

  function resetChat() {
    abortRef.current?.abort();
    abortRef.current = null;
    inFlightRef.current = false;
    setLoading(false);
    const next = makeConversationId();
    setConversationId(next);
    setMessages([makeWelcome()]);
    setError(null);
    setStreamingStarted(false);
  }

  function regenerate() {
    if (!lastPrompt || loading) return;
    setMessages((current) => {
      const trimmed = [...current];
      if (trimmed.at(-1)?.role === "assistant") trimmed.pop();
      if (trimmed.at(-1)?.role === "user") trimmed.pop();
      return trimmed;
    });
    window.setTimeout(() => void interact(lastPrompt), 0);
  }

  return (
    <main className="messenger-shell">
      <section className="chat-panel">
        <ChatHeader
          loading={loading}
          streaming={streamingStarted}
          dark={dark}
          onToggleTheme={() => setDark((value) => !value)}
          onNewChat={resetChat}
        />

        <div ref={messageScrollRef} className="message-scroll" aria-live="polite" aria-busy={loading}>
          <div className="conversation-date"><span>Hôm nay</span></div>
          <div className="message-stream">
            {messages.map((message, index) => (
              <MessageItem
                key={message.id}
                message={message}
                latest={index === messages.length - 1}
                loading={loading}
                streaming={loading && streamingStarted}
                onRegenerate={regenerate}
              />
            ))}

            {loading && !streamingStarted && (
              <div className="message-row assistant">
                <span className="message-avatar"><BotIcon /></span>
                <div><div className="typing"><i /><i /><i /></div><small className="typing-label">Kori đang suy nghĩ</small></div>
              </div>
            )}

            {error && (
              <div className="error-banner">
                <span><strong>Không gửi được tin nhắn</strong>{error}</span>
                <button onClick={() => { setError(null); if (lastPrompt) void interact(lastPrompt); }}>Thử lại</button>
              </div>
            )}

          </div>
          <div className="scroll-anchor" />
        </div>

        <MessageComposer
          value={input}
          loading={loading}
          onChange={setInput}
          onSubmit={submit}
          onStop={() => abortRef.current?.abort()}
        />
      </section>
    </main>
  );
}
