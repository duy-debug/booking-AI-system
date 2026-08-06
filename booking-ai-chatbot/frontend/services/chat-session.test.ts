import { describe, expect, it, vi } from "vitest";
import {
  CHAT_SESSION_KEY,
  CHAT_SESSION_TTL_MS,
  loadConversationId,
  getOrCreateConversationId,
  resetConversationId,
  saveConversationSession,
} from "./chat-session";

describe("chat session", () => {
  it("reuses a non-expired conversation", () => {
    const storage = {
      getItem: vi.fn(() => JSON.stringify({ conversationId: "c-1", updatedAt: 1_000 })),
      removeItem: vi.fn(),
    };
    expect(loadConversationId(storage, 1_000 + CHAT_SESSION_TTL_MS - 1)).toBe("c-1");
  });

  it("discards an expired conversation", () => {
    const storage = {
      getItem: vi.fn(() => JSON.stringify({ conversationId: "c-1", updatedAt: 1_000 })),
      removeItem: vi.fn(),
    };
    expect(loadConversationId(storage, 1_000 + CHAT_SESSION_TTL_MS)).toBeNull();
    expect(storage.removeItem).toHaveBeenCalledWith(CHAT_SESSION_KEY);
  });

  it("stores the conversation with its activity time", () => {
    const storage = { setItem: vi.fn() };
    saveConversationSession(storage, "c-2", 2_000);
    expect(storage.setItem).toHaveBeenCalledWith(
      CHAT_SESSION_KEY,
      JSON.stringify({ conversationId: "c-2", updatedAt: 2_000 }),
    );
  });

  it("keeps one conversation id across calls", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    };
    const first = getOrCreateConversationId(storage);
    expect(getOrCreateConversationId(storage)).toBe(first);
  });

  it("reset creates a different conversation id", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    };
    const first = getOrCreateConversationId(storage);
    expect(resetConversationId(storage)).not.toBe(first);
  });
});
