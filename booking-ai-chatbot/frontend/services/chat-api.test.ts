import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatResponse } from "@/types/chat";
import { ChatApiError, sendChat, streamChat } from "./chat-api";

const chatResponse: ChatResponse = {
  conversation_id: "conversation-1",
  text: "Xin chào",
  state: "selecting_shop",
  status: "success",
  instruction_template: null,
  quick_replies: ["Shibuya", "Shinjuku"],
  metadata: { source: "booking" },
};

function streamResponse(chunks: string[], status = 200) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "Content-Type": "text/event-stream" } });
}

function successSse(response = chatResponse, newline = "\n") {
  return [
    "event: started",
    `data: ${JSON.stringify({ conversation_id: response.conversation_id })}`,
    "",
    "event: message",
    `data: ${JSON.stringify(response)}`,
    "",
    "event: completed",
    `data: ${JSON.stringify({
      conversation_id: response.conversation_id,
      stream_status: "completed",
      dialog_status: response.status,
    })}`,
    "",
    "",
  ].join(newline);
}

afterEach(() => vi.restoreAllMocks());

describe("streamChat", () => {
  it("sends the exact new request and parses started/message/completed", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([successSse()]));
    const onStarted = vi.fn();
    const onMessage = vi.fn();
    const onCompleted = vi.fn();

    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "  xin chào  ",
    }, { onStarted, onMessage, onCompleted })).resolves.toEqual(chatResponse);

    const init = fetchMock.mock.calls[0][1];
    expect(JSON.parse(String(init?.body))).toEqual({
      conversation_id: "conversation-1",
      message: "xin chào",
    });
    expect(String(init?.body)).not.toContain("query");
    expect(String(init?.body)).not.toContain("selection");
    expect(onStarted).toHaveBeenCalledOnce();
    expect(onMessage).toHaveBeenCalledOnce();
    expect(onCompleted).toHaveBeenCalledOnce();
  });

  it("parses events split across TCP chunks and multiple events per chunk", async () => {
    const payload = successSse();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([
      payload.slice(0, 23),
      payload.slice(23, 91),
      payload.slice(91),
    ]));
    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "hello",
    })).resolves.toEqual(chatResponse);
  });

  it("supports CRLF framing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([successSse(chatResponse, "\r\n")]));
    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "hello",
    })).resolves.toEqual(chatResponse);
  });

  it("accepts the existing-booking cancellation identity state", async () => {
    const response: ChatResponse = {
      ...chatResponse,
      state: "collecting_cancel_booking_identity",
      text: "Để hủy booking đã đặt, anh/chị vui lòng cung cấp mã booking và số điện thoại.",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([successSse(response)]));

    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "tôi muốn hủy booking",
    })).resolves.toEqual(response);
  });

  it("accepts the existing-booking cancellation confirmation state", async () => {
    const response: ChatResponse = {
      ...chatResponse,
      state: "awaiting_cancel_confirmation",
      text: "Anh/chá»‹ cÃ³ cháº¯c cháº¯n muá»‘n há»§y booking nÃ y khÃ´ng?",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([successSse(response)]));

    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "0901234567 vÃ  BK-1",
    })).resolves.toEqual(response);
  });

  it("supports multiline data and ignores unknown events", async () => {
    const pretty = JSON.stringify(chatResponse, null, 2)
      .split("\n")
      .map((line) => `data: ${line}`)
      .join("\n");
    const events = [
      "event: future_event\ndata: {}\n\n",
      "event: started\ndata: {\"conversation_id\":\"conversation-1\"}\n\n",
      `event: message\n${pretty}\n\n`,
      "event: completed\ndata: {\"conversation_id\":\"conversation-1\",\"stream_status\":\"completed\",\"dialog_status\":\"success\"}\n\n",
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse(events));
    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "hello",
    })).resolves.toEqual(chatResponse);
  });

  it("does not require token or done events", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([successSse()]));
    const onMessage = vi.fn();
    await streamChat({
      conversation_id: "conversation-1",
      message: "hello",
    }, { onMessage });
    expect(onMessage).toHaveBeenCalledWith(chatResponse);
  });

  it("parses assistant delta events before the final message", async () => {
    const onDelta = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([
      "event: started\ndata: {\"conversation_id\":\"conversation-1\"}\n\n",
      "event: delta\ndata: {\"conversation_id\":\"conversation-1\",\"text\":\"Xin\"}\n\n",
      "event: delta\ndata: {\"conversation_id\":\"conversation-1\",\"text\":\" chÃ o\"}\n\n",
      successSse(),
    ]));

    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "hello",
    }, { onDelta })).resolves.toEqual(chatResponse);

    expect(onDelta).toHaveBeenNthCalledWith(1, {
      conversation_id: "conversation-1",
      text: "Xin",
    });
    expect(onDelta).toHaveBeenNthCalledWith(2, {
      conversation_id: "conversation-1",
      text: " chÃ o",
    });
  });

  it("maps an SSE error message without reporting missing completed", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([
      "event: error\ndata: {\"conversation_id\":\"conversation-1\",\"code\":\"chat_processing_failed\",\"message\":\"Thử lại sau\"}\n\n",
    ]));
    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "hello",
    })).rejects.toMatchObject({
      problem: { code: "backend_internal_error", detail: "Thử lại sau" },
    });
  });

  it("marks a stream without completed or error as truncated", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(streamResponse([
      `event: message\ndata: ${JSON.stringify(chatResponse)}\n\n`,
    ]));
    await expect(streamChat({
      conversation_id: "conversation-1",
      message: "hello",
    })).rejects.toMatchObject({ problem: { code: "stream_interrupted" } });
  });

  it("rejects an empty message before fetch", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await expect(streamChat({ conversation_id: "c", message: "   " }))
      .rejects.toThrow("Tin nhắn không được để trống");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reads FastAPI 422 detail safely", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      detail: [{ msg: "Field required" }, { msg: "Extra inputs are not permitted" }],
    }), { status: 422, headers: { "Content-Type": "application/json" } }));
    await expect(streamChat({ conversation_id: "c", message: "hello" }))
      .rejects.toMatchObject({
        problem: {
          status: 422,
          code: "backend_validation_error",
          detail: "Tin nhắn không hợp lệ. Vui lòng kiểm tra và thử lại.",
        },
      });
  });

  it("uses a safe fallback for non-JSON HTTP errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("gateway failed", { status: 502 }));
    await expect(streamChat({ conversation_id: "c", message: "hello" }))
      .rejects.toBeInstanceOf(ChatApiError);
  });

  it("propagates AbortController cancellation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => new Promise(
      (_resolve, reject) => init?.signal?.addEventListener("abort", () => {
        reject(new DOMException("Aborted", "AbortError"));
      }),
    ));
    const controller = new AbortController();
    const request = streamChat({ conversation_id: "c", message: "hello", signal: controller.signal });
    controller.abort();
    await expect(request).rejects.toMatchObject({ problem: { code: "cancelled" } });
  });

  it("cancels an opened SSE reader and does not render the final message", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(
          "event: started\ndata: {\"conversation_id\":\"conversation-1\"}\n\n",
        ));
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
    const onStarted = vi.fn();
    const onMessage = vi.fn();
    const controller = new AbortController();
    const request = streamChat({
      conversation_id: "conversation-1",
      message: "hello",
      signal: controller.signal,
    }, { onStarted, onMessage });

    await new Promise((resolve) => globalThis.setTimeout(resolve, 0));
    expect(onStarted).toHaveBeenCalledOnce();
    controller.abort();

    await expect(request).rejects.toMatchObject({ problem: { code: "cancelled" } });
    expect(onMessage).not.toHaveBeenCalled();
  });
});

describe("sendChat", () => {
  it("posts the exact JSON contract and parses the response", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(chatResponse),
    );
    await expect(sendChat({ conversation_id: "conversation-1", message: " xin chào " }))
      .resolves.toEqual(chatResponse);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      conversation_id: "conversation-1",
      message: "xin chào",
    });
  });

  it("does not expose an HTTP 500 response body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("private traceback", { status: 500 }),
    );
    await expect(sendChat({ conversation_id: "c", message: "hello" }))
      .rejects.toMatchObject({
        problem: { code: "backend_internal_error", detail: expect.not.stringContaining("private") },
      });
  });
});
