"use client";

interface ChatErrorBannerProps {
  error: string;
  canRetry: boolean;
  loading: boolean;
  onRetry: () => void;
}

// Banner lỗi thân thiện cho người dùng, chỉ cho retry khi request trước đó an toàn để gửi lại.
export function ChatErrorBanner({
  error,
  canRetry,
  loading,
  onRetry,
}: ChatErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      <span>
        <strong>Không gửi được tin nhắn</strong>
        {error}
      </span>
      {canRetry && (
        <button disabled={loading} onClick={onRetry} type="button">
          Thử lại
        </button>
      )}
    </div>
  );
}
