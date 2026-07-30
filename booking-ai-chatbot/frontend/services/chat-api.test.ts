import { afterEach, describe, expect, it, vi } from "vitest";
import { streamChat, transcribeAudio } from "./chat-api";

afterEach(() => vi.restoreAllMocks());

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

  it("supports the standard unnamed message event", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          "data: {\"delta\":\"Xin chào\"}\n\n"
          + "event: done\ndata: {\"contract_version\":\"1.0\",\"answer\":\"Xin chào\",\"intent\":\"general\",\"conversation_id\":\"c\"}\n\n",
        ));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status: 200 }));
    const deltas: string[] = [];

    await streamChat(
      { conversationId: "c", query: "hello" },
      { onToken: (delta) => deltas.push(delta) },
    );

    expect(deltas).toEqual(["Xin chào"]);
  });

  it("rejects a stream closed before done", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          "event: token\ndata: {\"delta\":\"partial\"}\n\n",
        ));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status: 200 }));

    await expect(streamChat({ conversationId: "c", query: "hello" }))
      .rejects.toThrow("without a done event");
  });

  it("does not call onDone twice for duplicate done events", async () => {
    const done = "{\"contract_version\":\"1.0\",\"answer\":\"ok\",\"intent\":\"general\",\"conversation_id\":\"c\"}";
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `event: done\ndata: ${done}\n\nevent: done\ndata: ${done}\n\n`,
        ));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status: 200 }));
    const onDone = vi.fn();

    await streamChat({ conversationId: "c", query: "hello" }, { onDone });

    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("surfaces malformed SSE JSON", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("event: token\ndata: {bad-json}\n\n"));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status: 200 }));

    await expect(streamChat({ conversationId: "c", query: "hello" }))
      .rejects.toBeInstanceOf(SyntaxError);
  });

  it("propagates AbortController cancellation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => new Promise(
      (_resolve, reject) => init?.signal?.addEventListener("abort", () => {
        reject(new DOMException("Aborted", "AbortError"));
      }),
    ));
    const controller = new AbortController();
    const request = streamChat({
      conversationId: "c",
      query: "hello",
      signal: controller.signal,
    });
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("transcribeAudio", () => {
  it("uploads the recording and returns Vietnamese text", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ text: "Tôi muốn đặt lịch ngày mai." }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(transcribeAudio(new Blob(["audio"], { type: "audio/webm" })))
      .resolves.toBe("Tôi muốn đặt lịch ngày mai.");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/audio/transcriptions",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
  });
});
