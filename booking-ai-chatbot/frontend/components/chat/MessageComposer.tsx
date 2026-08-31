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

// Ô nhập tin nhắn: giữ nút gửi cố định, khi loading thì cùng nút này đóng vai trò dừng stream.
export function MessageComposer({ value, loading, onChange, onSubmit, onStop }: Props) {
  // Submit khi đang loading sẽ gọi abort để người dùng dừng câu trả lời hiện tại.
  function submit(event: FormEvent) {
    event.preventDefault();
    if (loading) {
      onStop();
      return;
    }
    onSubmit();
  }

  // Enter gửi tin nhắn, Shift+Enter vẫn xuống dòng để nhập nội dung dài.
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
