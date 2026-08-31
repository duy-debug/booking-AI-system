"use client";

import { BotIcon, CheckIcon } from "@/components/common/Icons";
import type { ChatMessage } from "@/types/chat";

interface Props {
  message: ChatMessage;
  latest: boolean;
  streaming: boolean;
}

// Format timestamp theo tiếng Việt để metadata tin nhắn đồng bộ với UX chatbot.
function timeLabel(timestamp: number) {
  if (!timestamp) return "Bây giờ";
  return new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit" }).format(timestamp);
}

// Nhận diện dòng có cấu trúc để giữ layout list/form booking không bị gộp thành đoạn văn.
function isStructuredLine(line: string) {
  return (
    line.startsWith("- ")
    || /^\d+\.\s+\S/.test(line)
    || /^[^:]{1,80}:\s*\S*$/.test(line)
  );
}

// Gom các dòng văn bản thường thành một đoạn sạch sau khi đã loại khoảng trắng thừa.
function normalizeParagraphLines(lines: string[]) {
  return lines.map((line) => line.trim()).filter(Boolean).join(" ");
}

// Tách câu hội thoại thường thành hai đoạn để bubble dễ đọc hơn khi LLM trả lời dài.
function splitPlainParagraphs(lines: string[]) {
  const text = normalizeParagraphLines(lines);
  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.map((sentence) => sentence.trim()) ?? [];
  if (sentences.length < 2) return [text];
  return [
    sentences.slice(0, -1).join(" "),
    sentences.at(-1) ?? "",
  ].filter(Boolean);
}

// Gán class theo loại dòng để CSS trình bày list, spacer và thông tin chi tiết khác nhau.
function lineClassName(line: string) {
  if (!line.trim()) return "message-line spacer";
  if (line.startsWith("- ")) return "message-line detail";
  return "message-line";
}

// Render nội dung message, ưu tiên giữ cấu trúc form/list nhưng vẫn hỗ trợ code block khi có.
function MessageBody({ text }: { text: string }) {
  if (!text.includes("```")) {
    const lines = text.split("\n");
    const hasStructuredLines = lines.some((line) => isStructuredLine(line.trim()));
    if (!hasStructuredLines) {
      const paragraphs = splitPlainParagraphs(lines);
      if (paragraphs.length === 1) return <span>{paragraphs[0]}</span>;
      return (
        <span className="message-lines plain-paragraphs">
          {paragraphs.map((paragraph, index) => (
            <span className="message-line paragraph" key={`${index}-${paragraph}`}>
              {paragraph}
            </span>
          ))}
        </span>
      );
    }

    return (
      <span className="message-lines">
        {lines.map((line, index) => (
          <span
            className={lineClassName(line)}
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

// Render một tin nhắn trong conversation, gồm avatar bot, bubble, timestamp và trạng thái gửi.
export function MessageItem({ message, latest, streaming }: Props) {
  const showStreamingCaret = message.role === "assistant" && streaming && latest;

  return (
    <article className={`message-row ${message.role}${message.text ? "" : " empty"}`}>
      {message.role === "assistant" && <span className="message-avatar"><BotIcon /></span>}
      <div className="message-content">
        <div className={`bubble ${showStreamingCaret ? "streaming" : ""}`}>
          <MessageBody text={message.text} />
        </div>
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
