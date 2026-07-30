"use client";

import { useState } from "react";
import { BotIcon, CheckIcon, CopyIcon, RefreshIcon, ThumbsDownIcon, ThumbsUpIcon } from "@/components/common/Icons";
import type { ChatMessage } from "@/types/chat";

interface Props {
  message: ChatMessage;
  latest: boolean;
  loading: boolean;
  streaming: boolean;
  onRegenerate: () => void;
}

function timeLabel(timestamp: number) {
  if (!timestamp) return "Bây giờ";
  return new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(timestamp);
}

function MessageBody({ text }: { text: string }) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((part, index) => {
    if (!part.startsWith("```")) return <span key={index}>{part}</span>;
    const content = part.slice(3, -3);
    const newline = content.indexOf("\n");
    const language = newline > 0 ? content.slice(0, newline).trim() : "";
    const code = newline > 0 ? content.slice(newline + 1) : content;
    return (
      <span className="code-block" key={index}>
        <span className="code-header">{language || "Code"}</span>
        <code>{code}</code>
      </span>
    );
  });
}

export function MessageItem({ message, latest, loading, streaming, onRegenerate }: Props) {
  const [copied, setCopied] = useState(false);
  const [reaction, setReaction] = useState<"up" | "down" | null>(null);

  async function copyMessage() {
    await navigator.clipboard.writeText(message.text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <article className={`message-row ${message.role}${message.text ? "" : " empty"}`}>
      {message.role === "assistant" && <span className="message-avatar"><BotIcon /></span>}
      <div className="message-content">
        <div className={`bubble ${streaming && latest ? "streaming" : ""}`}><MessageBody text={message.text} /></div>
        <div className="message-meta">
          <time>{timeLabel(message.createdAt)}</time>
          {message.role === "user" ? (
            <span className="delivery-status"><CheckIcon /><CheckIcon /> Đã xem</span>
          ) : message.text ? (
            <span className="message-tools">
              <button onClick={() => void copyMessage()} title="Sao chép"><CopyIcon />{copied && <em>Đã chép</em>}</button>
              <button className={reaction === "up" ? "selected" : ""} onClick={() => setReaction(reaction === "up" ? null : "up")} title="Hữu ích"><ThumbsUpIcon /></button>
              <button className={reaction === "down" ? "selected" : ""} onClick={() => setReaction(reaction === "down" ? null : "down")} title="Không hữu ích"><ThumbsDownIcon /></button>
              {latest && !loading && <button onClick={onRegenerate} title="Tạo lại"><RefreshIcon /></button>}
            </span>
          ) : null}
        </div>
      </div>
    </article>
  );
}
