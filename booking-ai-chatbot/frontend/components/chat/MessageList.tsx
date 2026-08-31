"use client";

import type { RefObject } from "react";
import { ChatErrorBanner } from "@/components/chat/ChatErrorBanner";
import { MessageItem } from "@/components/chat/MessageItem";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import type { ChatMessage } from "@/types/chat";

interface MessageListProps {
  messages: ChatMessage[];
  loading: boolean;
  streamingStarted: boolean;
  error: string | null;
  canRetry: boolean;
  scrollRef: RefObject<HTMLDivElement | null>;
  onRetry: () => void;
  onScrollNearBottomChange: (nearBottom: boolean) => void;
}

// Hiển thị luồng tin nhắn, thinking indicator và lỗi gửi trong cùng vùng scroll của chat.
export function MessageList({
  messages,
  loading,
  streamingStarted,
  error,
  canRetry,
  scrollRef,
  onRetry,
  onScrollNearBottomChange,
}: MessageListProps) {
  const latestMessage = messages.at(-1);
  // Chỉ hiển thị typing bubble khi chưa có assistant delta/message thật để tránh render trùng.
  const showTypingIndicator = loading && latestMessage?.role !== "assistant";

  return (
    <div
      ref={scrollRef}
      className="message-scroll"
      aria-live="polite"
      aria-busy={loading}
      onScroll={(event) => {
        const element = event.currentTarget;
        onScrollNearBottomChange(
          element.scrollHeight - element.scrollTop - element.clientHeight < 120,
        );
      }}
    >
      <div className="conversation-date">
        <span>Hôm nay</span>
      </div>

      <div className="message-stream">
        {messages.map((message, index) => (
          <MessageItem
            key={message.id}
            message={message}
            latest={index === messages.length - 1}
            streaming={loading && streamingStarted}
          />
        ))}

        {showTypingIndicator && <TypingIndicator />}

        {error && (
          <ChatErrorBanner
            error={error}
            canRetry={canRetry}
            loading={loading}
            onRetry={onRetry}
          />
        )}
      </div>

      <div className="scroll-anchor" />
    </div>
  );
}
