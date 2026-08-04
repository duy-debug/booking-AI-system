"use client";

import { useEffect, useRef, useState } from "react";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { MessageComposer } from "@/components/chat/MessageComposer";
import { MessageItem } from "@/components/chat/MessageItem";
import { BotIcon } from "@/components/common/Icons";
import { ChatApiError, streamChat } from "@/services/chat-api";
import { saveConversationSession } from "@/services/chat-session";
import type { ChatMessage } from "@/types/chat";

const WELCOME_TEXT = "Xin chào! Mình là Kori, trợ lý wellness của Komorebi. Mình có thể giúp bạn đặt lịch và giải đáp thông tin dịch vụ. Hôm nay bạn cần mình hỗ trợ gì?";

interface ChatAttempt {
  userMessage: string;
  idempotencyKey: string;
  conversationId: string;
}

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
  const [failedAttempt, setFailedAttempt] = useState<ChatAttempt | null>(null);
  const [dark, setDark] = useState(false);
  const messageScrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      localStorage.removeItem("booking-chat-conversation");
      localStorage.removeItem("booking-chat-session");
      const nextConversation = makeConversationId();
      setConversationId(nextConversation);
      setDark(localStorage.getItem("booking-chat-theme") === "dark");
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

  function removeLatestTurn() {
    setMessages((current) => {
      const trimmed = [...current];
      if (trimmed.at(-1)?.role === "assistant") trimmed.pop();
      if (trimmed.at(-1)?.role === "user") trimmed.pop();
      return trimmed;
    });
  }

  async function interact(attempt: ChatAttempt, replaceLatest = false) {
    if (!attempt.userMessage.trim() || attempt.conversationId !== conversationId || inFlightRef.current) return;
    inFlightRef.current = true;
    if (replaceLatest) removeLatestTurn();
    saveConversationSession(localStorage, conversationId);
    const assistantMessageId = crypto.randomUUID();
    const controller = new AbortController();
    abortRef.current = controller;
    setFailedAttempt(null);
    setError(null);
    setStreamingStarted(false);
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: attempt.userMessage, createdAt: Date.now() },
      { id: assistantMessageId, role: "assistant", text: "", createdAt: Date.now() },
    ]);
    setLoading(true);

    try {
      await streamChat(
        {
          conversation_id: attempt.conversationId,
          message: attempt.userMessage,
          idempotency_key: attempt.idempotencyKey,
          signal: controller.signal,
        },
        {
          onStarted: () => setStreamingStarted(true),
          onMessage: (response) => {
            setMessages((current) => current.map((message) => (
              message.id === assistantMessageId
                ? { ...message, text: response.text, response }
                : message
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
        setFailedAttempt(attempt);
        const truncated = cause instanceof Error && cause.message.includes("ended unexpectedly");
        setError(truncated
          ? "Kết nối bị gián đoạn; yêu cầu có thể đã được xử lý. Bạn có thể thử lại an toàn với cùng mã yêu cầu."
          : cause instanceof ChatApiError
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

  function sendNewTurn(userText: string) {
    const trimmed = userText.trim();
    if (!trimmed || loading || inFlightRef.current || !conversationId) return;
    const attempt: ChatAttempt = {
      userMessage: trimmed,
      idempotencyKey: crypto.randomUUID(),
      conversationId,
    };
    void interact(attempt);
  }

  function submit() {
    const value = input.trim();
    if (!value || loading) return;
    setInput("");
    sendNewTurn(value);
  }

  function resetChat() {
    abortRef.current?.abort();
    abortRef.current = null;
    inFlightRef.current = false;
    const next = makeConversationId();
    setConversationId(next);
    setMessages([makeWelcome()]);
    setInput("");
    setLoading(false);
    setError(null);
    setFailedAttempt(null);
    setStreamingStarted(false);
  }

  function retry() {
    if (!failedAttempt || loading) return;
    void interact(failedAttempt, true);
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
                onQuickReply={sendNewTurn}
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
                <button disabled={loading} onClick={retry}>Thử lại</button>
              </div>
            )}
          </div>
          <div className="scroll-anchor" />
        </div>

        {conversationId && (
          <MessageComposer
            value={input}
            loading={loading}
            onChange={setInput}
            onSubmit={submit}
            onStop={() => abortRef.current?.abort()}
          />
        )}
      </section>
    </main>
  );
}
