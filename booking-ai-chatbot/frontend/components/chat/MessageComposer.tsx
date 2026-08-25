"use client";

import type { FormEvent, KeyboardEvent } from "react";
import { SendIcon, StopIcon } from "@/components/common/Icons";

interface Props {
  value: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
}

export function MessageComposer({ value, loading, onChange, onSubmit, onStop }: Props) {
  function submit(event: FormEvent) {
    event.preventDefault();
    if (loading) {
      onStop();
      return;
    }
    onSubmit();
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <footer className="composer-wrap">
      <form className="composer" onSubmit={submit}>
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={keyDown}
          placeholder="Nhắn tin cho Kori..."
          rows={1}
          maxLength={2000}
          aria-label="Tin nhắn"
          disabled={loading}
        />
        <div className="composer-submit">
          <button
            type="submit"
            className="send-button"
            aria-label={loading ? "Dừng câu trả lời" : "Gửi tin nhắn"}
            disabled={!loading && !value.trim()}
            data-loading={loading ? "true" : "false"}
          >
            <span className="send-button-icon">
              <SendIcon />
            </span>
            <span className="send-button-stop" aria-hidden="true">
              <StopIcon />
            </span>
          </button>
        </div>
      </form>
      <p>Kori có thể mắc lỗi. Vui lòng kiểm tra lại thông tin quan trọng.</p>
    </footer>
  );
}
