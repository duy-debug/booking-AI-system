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

function isStructuredLine(line: string) {
  return (
    line.startsWith("- ")
    || /^\d+\.\s+\S/.test(line)
    || /^[^:]{1,80}:\s*\S*$/.test(line)
  );
}

function normalizeParagraphLines(lines: string[]) {
  return lines.map((line) => line.trim()).filter(Boolean).join(" ");
}

function splitPlainParagraphs(lines: string[]) {
  const text = normalizeParagraphLines(lines);
  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.map((sentence) => sentence.trim()) ?? [];
  if (sentences.length < 2) return [text];
  return [
    sentences.slice(0, -1).join(" "),
    sentences.at(-1) ?? "",
  ].filter(Boolean);
}

function lineClassName(line: string) {
  if (!line.trim()) return "message-line spacer";
  if (line.startsWith("- ")) return "message-line detail";
  return "message-line";
}

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
