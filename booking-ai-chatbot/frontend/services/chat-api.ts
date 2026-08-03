import type {
  ChatCompletedEvent,
  ChatErrorEvent,
  ChatProblem,
  ChatRequest,
  ChatResponse,
  ChatStartedEvent,
} from "@/types/chat";

export class ChatApiError extends Error {
  constructor(public readonly problem: ChatProblem) {
    super(problem.detail);
  }
}

interface ChatStreamCallbacks {
  onStarted?: (data: ChatStartedEvent) => void;
  onMessage?: (response: ChatResponse) => void;
  onCompleted?: (data: ChatCompletedEvent) => void;
}

interface StreamState {
  response?: ChatResponse;
  completed: boolean;
  errored: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(value: Record<string, unknown>, field: string): string {
  if (typeof value[field] !== "string") throw new Error(`Invalid SSE ${field}`);
  return value[field];
}

function parseStarted(value: unknown): ChatStartedEvent {
  if (!isRecord(value)) throw new Error("Invalid started event");
  return { conversation_id: stringField(value, "conversation_id") };
}

function parseResponse(value: unknown): ChatResponse {
  if (!isRecord(value)) throw new Error("Invalid message event");
  const quickReplies = value.quick_replies;
  const metadata = value.metadata;
  if (!Array.isArray(quickReplies) || !quickReplies.every((item) => typeof item === "string")) {
    throw new Error("Invalid SSE quick_replies");
  }
  if (!isRecord(metadata)) throw new Error("Invalid SSE metadata");
  const instruction = value.instruction_template;
  if (instruction !== null && typeof instruction !== "string") {
    throw new Error("Invalid SSE instruction_template");
  }
  return {
    conversation_id: stringField(value, "conversation_id"),
    text: stringField(value, "text"),
    state: stringField(value, "state"),
    status: stringField(value, "status"),
    instruction_template: instruction,
    quick_replies: quickReplies,
    metadata,
  };
}

function parseCompleted(value: unknown): ChatCompletedEvent {
  if (!isRecord(value) || value.stream_status !== "completed") {
    throw new Error("Invalid completed event");
  }
  return {
    conversation_id: stringField(value, "conversation_id"),
    stream_status: "completed",
    dialog_status: stringField(value, "dialog_status"),
  };
}

function parseStreamError(value: unknown): ChatErrorEvent {
  if (!isRecord(value)) throw new Error("Invalid error event");
  return {
    conversation_id: stringField(value, "conversation_id"),
    code: stringField(value, "code"),
    message: stringField(value, "message"),
  };
}

function parseHttpProblem(value: unknown, status: number): ChatProblem {
  if (!isRecord(value)) {
    return { status, code: "CHAT_REQUEST_FAILED", detail: "Yêu cầu chatbot không thành công." };
  }
  const detailValue = value.detail;
  const detail = typeof detailValue === "string"
    ? detailValue
    : Array.isArray(detailValue)
      ? detailValue
        .map((item) => isRecord(item) && typeof item.msg === "string" ? item.msg : null)
        .filter((item): item is string => item !== null)
        .join("; ")
      : "Yêu cầu chatbot không thành công.";
  return {
    status,
    code: typeof value.code === "string" ? value.code : "CHAT_REQUEST_FAILED",
    detail: detail || "Yêu cầu chatbot không thành công.",
  };
}

function dispatchSseEvent(
  block: string,
  callbacks: ChatStreamCallbacks,
  state: StreamState,
) {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length || state.completed || state.errored) return;

  const data: unknown = JSON.parse(dataLines.join("\n"));
  if (event === "started") {
    callbacks.onStarted?.(parseStarted(data));
  } else if (event === "message") {
    state.response = parseResponse(data);
    callbacks.onMessage?.(state.response);
  } else if (event === "completed") {
    const completed = parseCompleted(data);
    state.completed = true;
    callbacks.onCompleted?.(completed);
  } else if (event === "error") {
    const error = parseStreamError(data);
    state.errored = true;
    throw new ChatApiError({ code: error.code, detail: error.message });
  }
}

export async function streamChat(
  input: ChatRequest & { signal?: AbortSignal },
  callbacks: ChatStreamCallbacks = {},
): Promise<ChatResponse> {
  const message = input.message.trim();
  if (!message) throw new Error("Chat message must not be empty");
  const request: ChatRequest = {
    conversation_id: input.conversation_id,
    message,
    idempotency_key: input.idempotency_key ?? null,
  };
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      "X-Correlation-ID": crypto.randomUUID(),
    },
    body: JSON.stringify(request),
    signal: input.signal,
  });

  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ChatApiError(parseHttpProblem(body, response.status));
  }
  if (!response.body) throw new Error("SSE response body is unavailable");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const state: StreamState = { completed: false, errored: false };
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (block.trim()) dispatchSseEvent(block, callbacks, state);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }

  if (!state.completed) throw new Error("SSE stream ended unexpectedly before completed event");
  if (!state.response) throw new Error("SSE stream completed without a message event");
  return state.response;
}
