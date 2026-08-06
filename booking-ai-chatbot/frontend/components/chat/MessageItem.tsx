"use client";

import { useState } from "react";
import { BotIcon, CheckIcon, CopyIcon, ThumbsDownIcon, ThumbsUpIcon } from "@/components/common/Icons";
import type { ChatMessage } from "@/types/chat";

interface Props {
  message: ChatMessage;
  latest: boolean;
  loading: boolean;
  streaming: boolean;
  onQuickReply: (reply: string) => void;
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

const STATE_LABELS: Record<string, string> = {
  selecting_shop: "Chọn cửa hàng",
  selecting_date: "Chọn ngày",
  selecting_people: "Số người",
  selecting_duration: "Thời lượng",
  selecting_service: "Liệu trình",
  selecting_time: "Khung giờ",
  selecting_therapist: "Kỹ thuật viên",
  collecting_phone: "Số điện thoại",
  verifying_phone: "Xác minh",
  awaiting_confirmation: "Xác nhận cuối",
  completed: "Hoàn tất",
};

function suggestionTitle(message: ChatMessage) {
  const state = message.response?.state;
  if (state === "selecting_shop") return "Chọn cửa hàng";
  if (state === "selecting_service") {
    return message.text.toLocaleLowerCase("vi-VN").includes("add-on")
      ? "Chọn add-on (không bắt buộc)"
      : "Chọn liệu trình chính";
  }
  if (state === "selecting_time") return "Chọn khung giờ còn trống";
  return "Gợi ý trả lời";
}

export function MessageItem({ message, latest, loading, streaming, onQuickReply }: Props) {
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
        {message.role === "assistant"
          && latest
          && !["completed", "cancelled"].includes(message.response?.state ?? "")
          && (message.response?.quick_replies.length ?? 0) > 0 && (
          <div className="quick-actions" aria-label="Gợi ý trả lời">
            <div className="quick-actions-heading">
              <span>{suggestionTitle(message)}</span>
              <small>Chạm để chọn nhanh</small>
            </div>
            <div className="quick-actions-grid">
              {[...new Set(message.response?.quick_replies ?? [])].map((reply) => (
                <button key={reply} type="button" disabled={loading} onClick={() => onQuickReply(reply)}>
                  <strong>{reply}</strong><b aria-hidden="true">›</b>
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="message-meta">
          <time>{timeLabel(message.createdAt)}</time>
          {message.role === "user" ? (
            <span className="delivery-status">
              <CheckIcon /> {message.status === "failed" ? "Gửi thất bại" : "Đã gửi"}
            </span>
          ) : message.text ? (
            <>
              {message.response?.state && (
                <span className={`state-chip status-${message.response.status}`}>
                  {STATE_LABELS[message.response.state] ?? message.response.state}
                </span>
              )}
              <span className="message-tools">
                <button aria-label="Sao chép" onClick={() => void copyMessage()} title="Sao chép"><CopyIcon />{copied && <em>Đã chép</em>}</button>
                <button aria-label="Hữu ích" className={reaction === "up" ? "selected" : ""} onClick={() => setReaction(reaction === "up" ? null : "up")} title="Hữu ích"><ThumbsUpIcon /></button>
                <button aria-label="Không hữu ích" className={reaction === "down" ? "selected" : ""} onClick={() => setReaction(reaction === "down" ? null : "down")} title="Không hữu ích"><ThumbsDownIcon /></button>
              </span>
            </>
          ) : null}
        </div>
      </div>
    </article>
  );
}
