import { BotIcon, MoonIcon, RefreshIcon, SunIcon, XIcon } from "@/components/common/Icons";

interface Props {
  loading: boolean;
  streaming: boolean;
  dark: boolean;
  onToggleTheme: () => void;
  onNewChat: () => void;
  onClose?: () => void;
  showThemeToggle?: boolean;
}

export function ChatHeader({
  loading,
  streaming,
  dark,
  onToggleTheme,
  onNewChat,
  onClose,
  showThemeToggle = true,
}: Props) {
  return (
    <header className="chat-header">
      <div className="header-person">
        <span className="header-avatar"><BotIcon /><i /></span>
        <span className="header-person-copy">
          <strong>Kori AI Concierge</strong>
          <small className={loading ? "working" : ""}>
            {loading ? (streaming ? "Đang trả lời..." : "Đang suy nghĩ...") : "Đang hoạt động"}
          </small>
        </span>
      </div>
      <div className="header-actions">
        <button title="Cuộc trò chuyện mới" aria-label="Cuộc trò chuyện mới" onClick={onNewChat}><RefreshIcon /></button>
        {showThemeToggle && (
          <button title={dark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"} aria-label="Đổi giao diện" onClick={onToggleTheme}>
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
        )}
        {onClose && <button title="Đóng trợ lý" aria-label="Đóng trợ lý" onClick={onClose}><XIcon /></button>}
      </div>
    </header>
  );
}
