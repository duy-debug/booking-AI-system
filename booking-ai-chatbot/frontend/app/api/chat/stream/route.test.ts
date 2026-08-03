import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";

afterEach(() => vi.restoreAllMocks());

describe("chat stream proxy", () => {
  it("targets chatbot port 8001, forwards only allowed fields, and preserves SSE", async () => {
    const encoder = new TextEncoder();
    const upstream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode("event: started\ndata: {}\n\n"));
        controller.enqueue(encoder.encode("event: completed\ndata: {}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(upstream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    }));
    const request = new NextRequest("http://localhost:3002/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: "conversation-1",
        message: "Xin chào",
        idempotency_key: "attempt-1",
        query: "legacy",
        selection: { value: "legacy" },
      }),
    });

    const response = await POST(request);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8001/api/v1/chat/stream");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      conversation_id: "conversation-1",
      message: "Xin chào",
      idempotency_key: "attempt-1",
    });
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    expect(response.headers.get("x-accel-buffering")).toBe("no");
    await expect(response.text()).resolves.toBe(
      "event: started\ndata: {}\n\nevent: completed\ndata: {}\n\n",
    );
  });
});
