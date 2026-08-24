"use client";

import { BotIcon } from "@/components/common/Icons";

export function TypingIndicator() {
  return (
    <div className="message-row assistant typing-row" role="status" aria-live="polite">
      <span className="message-avatar">
        <BotIcon />
      </span>
      <div className="typing-content">
        <div className="typing-bubble" aria-label="Kori đang suy nghĩ">
          <span />
          <span />
          <span />
        </div>
        <small className="typing-label">Kori đang suy nghĩ</small>
      </div>
    </div>
  );
}
