"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { CHAT_SESSION_KEY } from "@/services/chat-session";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Error boundary bảo vệ phần UI chatbot để lỗi render không làm sập toàn bộ landing page.
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  // Bắt lỗi render ở cây UI để thay bằng màn hình khôi phục thay vì để toàn trang trắng.
  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  // Ghi lại lỗi UI phục vụ debug, không hiển thị stack trace kỹ thuật cho người dùng.
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Chat UI render failure", error, info.componentStack);
  }

  // Xóa session chat bị lỗi và reload để người dùng quay về trạng thái an toàn.
  private recover = () => {
    localStorage.removeItem(CHAT_SESSION_KEY);
    localStorage.removeItem("booking-chat-conversation");
    window.location.reload();
  };

  // Render fallback khi component con crash, còn bình thường thì giữ nguyên nội dung trang.
  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="fatal-error-card" role="alert">
        <span>Không thể hiển thị bước hội thoại</span>
        <h1>Giao diện vừa gặp lỗi.</h1>
        <p>Vui lòng tạo cuộc trò chuyện mới hoặc tải lại trang.</p>
        <button onClick={this.recover}>Tạo cuộc trò chuyện mới</button>
      </main>
    );
  }
}
