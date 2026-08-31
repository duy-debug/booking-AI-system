export const CHAT_SESSION_KEY = "booking-chat-session";
export const CHAT_SESSION_TTL_MS = 30 * 60 * 1000;

interface StoredChatSession {
  conversationId: string;
  updatedAt: number;
}

type SessionStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

// Đọc conversation hiện tại từ sessionStorage và loại bỏ session hết hạn hoặc dữ liệu legacy hỏng.
export function loadConversationId(
  storage: Pick<Storage, "getItem" | "removeItem">,
  now = Date.now(),
): string | null {
  const raw = storage.getItem(CHAT_SESSION_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as Partial<StoredChatSession>;
    if (
      typeof session.conversationId === "string"
      && session.conversationId.length > 0
      && typeof session.updatedAt === "number"
      && now - session.updatedAt < CHAT_SESSION_TTL_MS
    ) {
      return session.conversationId;
    }
  } catch {
    // Invalid or legacy storage is discarded below.
  }
  storage.removeItem(CHAT_SESSION_KEY);
  return null;
}

// Lưu lại conversation để đóng/mở popup không làm mất mạch hội thoại trong cùng phiên.
export function saveConversationSession(
  storage: Pick<Storage, "setItem">,
  conversationId: string,
  now = Date.now(),
) {
  storage.setItem(CHAT_SESSION_KEY, JSON.stringify({ conversationId, updatedAt: now }));
}

// Tái sử dụng conversation còn hạn hoặc tạo ID mới cho phiên chat mới.
export function getOrCreateConversationId(storage: SessionStorage): string {
  const existing = loadConversationId(storage);
  if (existing) return existing;
  const conversationId = crypto.randomUUID();
  saveConversationSession(storage, conversationId);
  return conversationId;
}

// Xóa session hiện tại khi người dùng chủ động tạo cuộc trò chuyện mới.
export function resetConversationId(storage: SessionStorage): string {
  storage.removeItem(CHAT_SESSION_KEY);
  return getOrCreateConversationId(storage);
}
