import { NextRequest, NextResponse } from "next/server";

const backendUrl = (process.env.CHATBOT_API_URL || "http://localhost:8001").replace(/\/$/, "");

export async function POST(request: NextRequest) {
  const correlationId = request.headers.get("x-correlation-id") || crypto.randomUUID();
  try {
    const response = await fetch(`${backendUrl}/api/v1/audio/transcriptions`, {
      method: "POST",
      headers: { "X-Correlation-ID": correlationId },
      body: await request.formData(),
      cache: "no-store",
      signal: request.signal,
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/json",
        "X-Correlation-ID": response.headers.get("x-correlation-id") || correlationId,
      },
    });
  } catch {
    return NextResponse.json(
      {
        status: 503,
        detail: "Không thể kết nối dịch vụ nhận dạng giọng nói.",
        code: "TRANSCRIPTION_UNAVAILABLE",
      },
      { status: 503, headers: { "X-Correlation-ID": correlationId } },
    );
  }
}
