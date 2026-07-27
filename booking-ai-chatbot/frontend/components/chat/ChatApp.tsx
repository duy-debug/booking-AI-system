"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { BotIcon, RefreshIcon, SendIcon, SparkIcon } from "@/components/common/Icons";
import { UiRenderer } from "@/components/chat/UiRenderer";
import { ChatApiError, streamChat } from "@/services/chat-api";
import type { ChatMessage, ChatSelection } from "@/types/chat";

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Konnichiwa! Mình là Kori — wellness concierge của Komorebi Tokyo. Hôm nay mình có thể giúp bạn tìm một khoảng nghỉ thật dịu dàng nhé?",
  createdAt: 0,
};

const quickActions = [
  { label: "Đặt lịch mới", prompt: "Tôi muốn đặt lịch", tone: "sage" },
  { label: "Tra cứu booking", prompt: "Tôi muốn tra cứu booking", tone: "sand" },
  { label: "Đổi lịch", prompt: "Tôi muốn đổi lịch", tone: "blue" },
  { label: "Hủy lịch", prompt: "Tôi muốn hủy lịch", tone: "rose" },
];

const makeConversationId = () => crypto.randomUUID();

export function ChatApp() {
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingStarted, setStreamingStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messageScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = makeConversationId();
      localStorage.setItem("booking-chat-conversation", next);
      setConversationId(next);
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (conversationId) localStorage.setItem("booking-chat-conversation", conversationId);
  }, [conversationId]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const container = messageScrollRef.current;
      if (container) {
        container.scrollTop = container.scrollHeight;
      }
    });
    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [messages, loading, streamingStarted]);

  async function interact(userText: string, selection?: ChatSelection) {
    if (!conversationId || loading) return;
    const assistantMessageId = crypto.randomUUID();
    setError(null);
    setStreamingStarted(false);
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: userText, createdAt: Date.now() },
      {
        id: assistantMessageId,
        role: "assistant",
        text: "",
        createdAt: Date.now(),
      },
    ]);
    setLoading(true);
    try {
      await streamChat(
        {
          conversationId,
          query: selection ? undefined : userText,
          selection,
        },
        {
          onToken: (delta) => {
            setStreamingStarted(true);
            setMessages((current) => current.map((message) => (
              message.id === assistantMessageId
                ? { ...message, text: message.text + delta }
                : message
            )));
          },
          onDone: (response) => {
            setMessages((current) => current.map((message) => (
              message.id === assistantMessageId
                ? { ...message, text: response.answer, response }
                : message
            )));
          },
        },
      );
    } catch (cause) {
      setMessages((current) => current.filter((message) => (
        message.id !== assistantMessageId || message.text.length > 0
      )));
      const detail = cause instanceof ChatApiError
        ? cause.problem.detail
        : "Không thể kết nối đến trợ lý. Vui lòng thử lại.";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = input.trim();
    if (!value) return;
    setInput("");
    void interact(value);
  }

  function resetChat() {
    const next = makeConversationId();
    localStorage.setItem("booking-chat-conversation", next);
    setConversationId(next);
    setMessages([{ ...WELCOME, id: crypto.randomUUID(), createdAt: Date.now() }]);
    setError(null);
    setStreamingStarted(false);
  }

  return (
    <main className="app-shell">
      <aside className="brand-panel">
        <div className="sun-orbit" aria-hidden="true"><i /><i /><i /></div>
        <div className="brand-top">
          <div className="brand-mark"><SparkIcon /></div>
          <span>KOMOREBI</span>
        </div>
        <div className="brand-story">
          <p className="eyebrow">TOKYO · WELLNESS STUDIO</p>
          <h1>Find light<br/><em>in the pause.</em></h1>
          <p className="brand-copy">Nơi ánh sáng len qua từng kẽ lá, cơ thể được thả lỏng và tâm trí tìm lại nhịp điệu riêng.</p>
        </div>
        <div className="wellness-quote">
          <span>木漏れ日</span>
          <p>Komorebi — ánh nắng dịu dàng xuyên qua tán lá. Một khoảnh khắc nhỏ, đủ để bạn trở về cân bằng.</p>
        </div>
        <div className="brand-foot"><span>GINZA · TOKYO</span><span>09:00 — 22:00</span></div>
      </aside>

      <section className="chat-panel">
        <header className="chat-header">
          <div className="assistant-identity">
            <div className="assistant-avatar"><BotIcon /></div>
            <div>
              <strong>Kori · Komorebi Concierge</strong>
              <span className={loading ? "stream-status active" : "stream-status"}>
                <i /> {loading ? (streamingStarted ? "Đang stream câu trả lời" : "Đang xử lý yêu cầu") : "Online · phản hồi ngay"}
              </span>
            </div>
          </div>
          <button type="button" className="icon-button" onClick={resetChat} title="Bắt đầu cuộc trò chuyện mới"><RefreshIcon /></button>
        </header>

        <div ref={messageScrollRef} className="message-scroll" aria-live="polite" aria-busy={loading}>
          <div className="conversation-date">HÔM NAY</div>
          {messages.map((message, index) => (
            <article key={message.id} className={`message-row ${message.role}${message.text ? "" : " empty"}`}>
              {message.role === "assistant" && <div className="mini-avatar"><SparkIcon /></div>}
              <div className="message-content">
                <div className={`bubble${loading && streamingStarted && index === messages.length - 1 ? " streaming" : ""}`}>{message.text}</div>
                {message.response?.ui && (
                  <UiRenderer
                    ui={message.response.ui}
                    disabled={loading || index !== messages.length - 1}
                    onSelect={(text, selection) => void interact(text, selection)}
                  />
                )}
              </div>
            </article>
          ))}
          {loading && !streamingStarted && <div className="message-row assistant"><div className="mini-avatar"><SparkIcon /></div><div className="typing"><i/><i/><i/></div></div>}
          {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError(null)}>Đóng</button></div>}
          {messages.length === 1 && (
            <div className="quick-actions">
              {quickActions.map((action) => (
                <button type="button" key={action.prompt} className={action.tone} onClick={() => void interact(action.prompt)} disabled={loading}>
                  <span>{action.label}</span><small>→</small>
                </button>
              ))}
            </div>
          )}
          <div className="scroll-anchor" aria-hidden="true" />
        </div>

        <footer className="composer-wrap">
          <form className="composer" onSubmit={submit}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Nhập tin nhắn của bạn..."
              rows={1}
              maxLength={2000}
              disabled={loading}
              aria-label="Tin nhắn"
            />
            <button type="submit" disabled={loading || !input.trim()} aria-label="Gửi tin nhắn"><SendIcon /></button>
          </form>
          <p>KOMOREBI AI CONCIERGE · Thông tin quan trọng sẽ được xác nhận trước khi đặt lịch</p>
        </footer>
      </section>
    </main>
  );
}
