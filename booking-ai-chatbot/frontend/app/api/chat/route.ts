import { NextRequest, NextResponse } from "next/server";

const backendUrl = (process.env.CHATBOT_API_URL || "http://localhost:8001").replace(/\/$/, "");

export async function POST(request: NextRequest) {
  const correlationId = request.headers.get("x-correlation-id") || crypto.randomUUID();
  try {
    const incoming: unknown = await request.json();
    const source = typeof incoming === "object" && incoming !== null
      ? incoming as Record<string, unknown>
      : {};
    const response = await fetch(`${backendUrl}/api/v1/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Correlation-ID": correlationId,
      },
      body: JSON.stringify({
        conversation_id: source.conversation_id,
        message: source.message,
      }),
      cache: "no-store",
      signal: request.signal,
    });
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json",
        "X-Correlation-ID": response.headers.get("x-correlation-id") || correlationId,
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Không thể kết nối đến trợ lý." },
      { status: 503, headers: { "X-Correlation-ID": correlationId } },
    );
  }
}
