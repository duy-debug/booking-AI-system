import { afterEach, describe, expect, it, vi } from "vitest";
import { sendChat, streamChat } from "./chat-api";

afterEach(() => vi.restoreAllMocks());

describe("sendChat", () => {
  it("sends the versioned chat payload through the BFF", async () => {
    const response = {
      contract_version: "1.0",
      answer: "Xin chào",
      intent: "general",
      conversation_id: "conversation-1",
      ui: null,
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(sendChat({
      conversationId: "conversation-1",
      query: "xin chào",
    })).resolves.toEqual(response);

    expect(fetchMock).toHaveBeenCalledWith("/api/chat", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        conversation_id: "conversation-1",
        query: "xin chào",
      }),
    }));
  });

  it("maps Problem Details to ChatApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        status: 429,
        code: "RATE_LIMIT_EXCEEDED",
        detail: "Thử lại sau",
      }), { status: 429 }),
    );

    await expect(sendChat({
      conversationId: "conversation-1",
      query: "hello",
    })).rejects.toMatchObject({
      problem: { code: "RATE_LIMIT_EXCEEDED" },
    });
  });
});

describe("streamChat", () => {
  it("parses token and done SSE events", async () => {
    const finalResponse = {
      contract_version: "1.0",
      answer: "Xin chào",
      intent: "general",
      conversation_id: "conversation-1",
      ui: null,
    } as const;
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          "event: start\ndata: {\"contract_version\":\"1.0\",\"conversation_id\":\"conversation-1\"}\n\n"
          + "event: token\ndata: {\"delta\":\"Xin \"}\n\n",
        ));
        controller.enqueue(encoder.encode(
          `event: token\ndata: {"delta":"chào"}\n\nevent: done\ndata: ${JSON.stringify(finalResponse)}\n\n`,
        ));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    }));
    const deltas: string[] = [];

    await expect(streamChat(
      { conversationId: "conversation-1", query: "hello" },
      { onToken: (delta) => deltas.push(delta) },
    )).resolves.toEqual(finalResponse);

    expect(deltas.join("")).toBe("Xin chào");
  });

  it("maps an SSE error event to ChatApiError", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          "event: error\ndata: {\"status\":503,\"code\":\"DEPENDENCY_UNAVAILABLE\",\"detail\":\"Thử lại sau\"}\n\n",
        ));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status: 200 }));

    await expect(streamChat({
      conversationId: "conversation-1",
      query: "hello",
    })).rejects.toMatchObject({
      problem: { code: "DEPENDENCY_UNAVAILABLE" },
    });
  });
});
