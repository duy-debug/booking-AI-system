export const CHAT_SESSION_KEY = "booking-chat-session";
export const CHAT_SESSION_TTL_MS = 30 * 60 * 1000;

interface StoredChatSession {
  conversationId: string;
  updatedAt: number;
}

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

export function saveConversationSession(
  storage: Pick<Storage, "setItem">,
  conversationId: string,
  now = Date.now(),
) {
  storage.setItem(CHAT_SESSION_KEY, JSON.stringify({ conversationId, updatedAt: now }));
}
