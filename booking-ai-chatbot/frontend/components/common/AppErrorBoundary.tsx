"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { CHAT_SESSION_KEY } from "@/services/chat-session";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Chat UI render failure", error, info.componentStack);
  }

  private recover = () => {
    localStorage.removeItem(CHAT_SESSION_KEY);
    localStorage.removeItem("booking-chat-conversation");
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="fatal-error-card" role="alert">
        <span>Không thể hiển thị bước hội thoại</span>
        <h1>Giao diện vừa gặp lỗi.</h1>
        <p>{this.state.error.message || "Lỗi render không xác định."}</p>
        <button onClick={this.recover}>Tạo cuộc trò chuyện mới</button>
      </main>
    );
  }
}
