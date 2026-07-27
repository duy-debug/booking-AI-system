import { NextRequest, NextResponse } from "next/server";

const backendUrl = (process.env.CHATBOT_API_URL || "http://localhost:8001").replace(/\/$/, "");

export async function POST(request: NextRequest) {
  const correlationId = request.headers.get("x-correlation-id") || crypto.randomUUID();
  try {
    const response = await fetch(`${backendUrl}/api/v1/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Correlation-ID": correlationId,
      },
      body: await request.text(),
      cache: "no-store",
      signal: request.signal,
    });

    if (!response.ok || !response.body) {
      const body = await response.text();
      return new NextResponse(body, {
        status: response.status,
        headers: {
          "Content-Type": response.headers.get("content-type") || "application/problem+json",
          "X-Correlation-ID": response.headers.get("x-correlation-id") || correlationId,
        },
      });
    }

    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "X-Correlation-ID": response.headers.get("x-correlation-id") || correlationId,
      },
    });
  } catch {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Chatbot unavailable",
        status: 503,
        detail: "Không thể kết nối đến trợ lý. Vui lòng thử lại.",
        code: "CHATBOT_UNAVAILABLE",
      },
      { status: 503, headers: { "X-Correlation-ID": correlationId } },
    );
  }
}
