"use client";

import type { FormEvent, KeyboardEvent } from "react";
import { SendIcon } from "@/components/common/Icons";

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
      {loading && <button className="stop-generation" onClick={onStop}>Dừng tạo nội dung</button>}
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
          {value.trim() && (
            <button type="submit" className="send-button" aria-label="Gửi tin nhắn" disabled={loading}>
              <SendIcon />
            </button>
          )}
        </div>
      </form>
      <p>Kori có thể mắc lỗi. Vui lòng kiểm tra lại thông tin quan trọng.</p>
    </footer>
  );
}
