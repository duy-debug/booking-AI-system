"use client";

interface ChatErrorBannerProps {
  error: string;
  canRetry: boolean;
  loading: boolean;
  onRetry: () => void;
}

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
