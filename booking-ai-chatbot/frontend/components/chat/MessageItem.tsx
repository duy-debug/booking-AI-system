"use client";

import { BotIcon, CheckIcon } from "@/components/common/Icons";
import type { ChatMessage } from "@/types/chat";

interface Props {
  message: ChatMessage;
  latest: boolean;
  streaming: boolean;
}

function timeLabel(timestamp: number) {
  if (!timestamp) return "Bây giờ";
  return new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(timestamp);
}

function MessageBody({ text }: { text: string }) {
  if (!text.includes("```")) {
    return (
      <span className="message-lines">
        {text.split("\n").map((line, index) => (
          <span
            className={line.startsWith("- ") ? "message-line detail" : "message-line"}
            key={`${index}-${line}`}
          >
            {line.startsWith("- ") ? line.slice(2) : line}
          </span>
        ))}
      </span>
    );
  }
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

export function MessageItem({ message, latest, streaming }: Props) {
  return (
    <article className={`message-row ${message.role}${message.text ? "" : " empty"}`}>
      {message.role === "assistant" && <span className="message-avatar"><BotIcon /></span>}
      <div className="message-content">
        <div className={`bubble ${streaming && latest ? "streaming" : ""}`}><MessageBody text={message.text} /></div>
        <div className="message-meta">
          <time>{timeLabel(message.createdAt)}</time>
          {message.role === "user" ? (
            <span className="delivery-status">
              <CheckIcon /> {message.status === "failed" ? "Gửi thất bại" : "Đã gửi"}
            </span>
          ) : null}
        </div>
      </div>
    </article>
  );
}
