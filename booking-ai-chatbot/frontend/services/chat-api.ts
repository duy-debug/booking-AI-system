import type { ChatResponse, ChatSelection, ProblemDetails } from "@/types/chat";

export class ChatApiError extends Error {
  constructor(public readonly problem: ProblemDetails) {
    super(problem.detail);
  }
}

export async function transcribeAudio(audio: Blob): Promise<string> {
  const form = new FormData();
  const extension = audio.type.includes("ogg") ? "ogg" : audio.type.includes("mp4") ? "m4a" : "webm";
  form.append("file", audio, `recording.${extension}`);
  const response = await fetch("/api/audio/transcriptions", {
    method: "POST",
    headers: { "X-Correlation-ID": crypto.randomUUID() },
    body: form,
  });
  const body = await response.json() as { text?: string } | ProblemDetails;
  if (!response.ok) throw new ChatApiError(body as ProblemDetails);
  return (body as { text: string }).text;
}

export async function sendChat(input: {
  conversationId: string;
  query?: string;
  selection?: ChatSelection;
}): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Correlation-ID": crypto.randomUUID(),
    },
    body: JSON.stringify({
      conversation_id: input.conversationId,
      query: input.query,
      selection: input.selection,
    }),
  });

  const body = (await response.json()) as ChatResponse | ProblemDetails;
  if (!response.ok) {
    throw new ChatApiError(body as ProblemDetails);
  }
  return body as ChatResponse;
}

interface ChatStreamCallbacks {
  onStart?: (data: { contract_version: "1.0"; conversation_id: string }) => void;
  onToken?: (delta: string) => void;
  onUi?: (ui: NonNullable<ChatResponse["ui"]>) => void;
  onDone?: (response: ChatResponse) => void;
}

function dispatchSseEvent(
  block: string,
  callbacks: ChatStreamCallbacks,
): ChatResponse | undefined {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return;

  const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
  if (event === "start") {
    callbacks.onStart?.(data as { contract_version: "1.0"; conversation_id: string });
  } else if (event === "token") {
    callbacks.onToken?.(String(data.delta ?? ""));
  } else if (event === "ui") {
    callbacks.onUi?.(data.ui as NonNullable<ChatResponse["ui"]>);
  } else if (event === "done") {
    const response = data as unknown as ChatResponse;
    callbacks.onDone?.(response);
    return response;
  } else if (event === "error") {
    throw new ChatApiError(data as unknown as ProblemDetails);
  }
}

export async function streamChat(
  input: {
    conversationId: string;
    query?: string;
    selection?: ChatSelection;
    signal?: AbortSignal;
  },
  callbacks: ChatStreamCallbacks = {},
): Promise<ChatResponse> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-Correlation-ID": crypto.randomUUID(),
    },
    body: JSON.stringify({
      conversation_id: input.conversationId,
      query: input.query,
      selection: input.selection,
    }),
    signal: input.signal,
  });

  if (!response.ok) {
    const problem = (await response.json()) as ProblemDetails;
    throw new ChatApiError(problem);
  }
  if (!response.body) {
    throw new Error("SSE response body is unavailable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: ChatResponse | undefined;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (block.trim()) {
        completed = dispatchSseEvent(block, callbacks) ?? completed;
      }
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }

  if (!completed) {
    throw new Error("SSE stream ended without a done event");
  }
  return completed;
}
