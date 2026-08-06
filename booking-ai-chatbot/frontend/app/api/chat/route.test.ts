import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";

afterEach(() => vi.restoreAllMocks());

describe("chat JSON proxy", () => {
  it("forwards only the backend ChatRequest fields", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({
        conversation_id: "conversation-1",
        text: "Xin chào",
        state: "idle",
        status: "success",
        instruction_template: null,
        quick_replies: [],
        metadata: {},
      }),
    );
    const request = new NextRequest("http://localhost:3002/api/chat", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: "conversation-1",
        message: "Xin chào",
        idempotency_key: "must-not-forward",
      }),
    });

    const response = await POST(request);

    expect(response.status).toBe(200);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      conversation_id: "conversation-1",
      message: "Xin chào",
    });
  });
});
