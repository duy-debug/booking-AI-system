import { SseParser, type ParsedSseEvent } from "./sse-parser";
import type {
  BookingState,
  ChatCompletedEvent,
  ChatDeltaEvent,
  ChatErrorCode,
  ChatProblem,
  ChatRequest,
  ChatResponse,
  ChatStartedEvent,
  DialogStatus,
  SafeMetadataValue,
} from "@/types/chat";

export class ChatApiError extends Error {
  constructor(public readonly problem: ChatProblem) {
    super(problem.detail);
  }
}

interface ChatStreamCallbacks {
  onStarted?: (data: ChatStartedEvent) => void;
  onDelta?: (data: ChatDeltaEvent) => void;
  onMessage?: (response: ChatResponse) => void;
  onCompleted?: (data: ChatCompletedEvent) => void;
}

const BOOKING_STATES = new Set<BookingState>([
  "idle", "collecting_cancel_booking_identity", "awaiting_cancel_confirmation",
  "selecting_shop", "selecting_date", "selecting_people",
  "selecting_duration", "selecting_service", "selecting_time",
  "selecting_therapist", "collecting_phone", "collecting_name",
  "verifying_phone", "awaiting_confirmation", "booking_executing",
  "completed", "booking_failed", "cancelled",
]);
const DIALOG_STATUSES = new Set<DialogStatus>([
  "success", "failure_handled", "failure_unhandled",
]);
const REQUEST_TIMEOUT_MS = 30_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringField(value: Record<string, unknown>, field: string): string {
  if (typeof value[field] !== "string") throw invalidResponse();
  return value[field];
}

function invalidResponse(): ChatApiError {
  return new ChatApiError({ code: "invalid_response", detail: "Phản hồi chatbot không hợp lệ." });
}

function cancelledRequest(): ChatApiError {
  return new ChatApiError({
    code: "cancelled",
    detail: "Yêu cầu đã được hủy.",
  });
}

function parseResponse(value: unknown): ChatResponse {
  if (!isRecord(value)) throw invalidResponse();
  const metadata = value.metadata;
  const state = stringField(value, "state");
  const status = stringField(value, "status");
  if (!BOOKING_STATES.has(state as BookingState) || !DIALOG_STATUSES.has(status as DialogStatus)) {
    throw invalidResponse();
  }
  if (!isRecord(metadata)) throw invalidResponse();
  const safeMetadata: Record<string, SafeMetadataValue> = {};
  for (const [key, item] of Object.entries(metadata)) {
    if (item === null || ["boolean", "number", "string"].includes(typeof item)) {
      safeMetadata[key] = item as SafeMetadataValue;
    } else {
      throw invalidResponse();
    }
  }
  const instruction = value.instruction_template;
  if (instruction !== null && typeof instruction !== "string") throw invalidResponse();
  return {
    conversation_id: stringField(value, "conversation_id"),
    text: stringField(value, "text"),
    state: state as BookingState,
    status: status as DialogStatus,
    instruction_template: instruction,
    metadata: safeMetadata,
  };
}

function parseProblem(status: number): ChatProblem {
  if (status === 422) {
    return {
      status,
      code: "backend_validation_error",
      detail: "Tin nhắn không hợp lệ. Vui lòng kiểm tra và thử lại.",
    };
  }
  return {
    status,
    code: "backend_internal_error",
    detail: "Hệ thống đang bận. Vui lòng thử lại sau.",
  };
}

function requestBody(input: ChatRequest): ChatRequest {
  const message = input.message.trim();
  if (!message) {
    throw new ChatApiError({ code: "invalid_response", detail: "Tin nhắn không được để trống." });
  }
  return { conversation_id: input.conversation_id, message };
}

async function fetchWithTimeout(
  url: string,
  input: ChatRequest,
  signal?: AbortSignal,
): Promise<Response> {
  const body = requestBody(input);
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
  const cancel = () => controller.abort("cancelled");
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    return await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: url.endsWith("/stream") ? "text/event-stream" : "application/json",
        "X-Correlation-ID": crypto.randomUUID(),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    if (controller.signal.aborted) {
      const code: ChatErrorCode = signal?.aborted ? "cancelled" : "timeout";
      throw new ChatApiError({
        code,
        detail: code === "cancelled" ? "Yêu cầu đã được hủy." : "Yêu cầu đã hết thời gian chờ.",
      });
    }
    throw new ChatApiError({ code: "network_error", detail: "Không thể kết nối đến trợ lý." });
  } finally {
    globalThis.clearTimeout(timeout);
    signal?.removeEventListener("abort", cancel);
  }
}

export async function sendChat(input: ChatRequest & { signal?: AbortSignal }): Promise<ChatResponse> {
  const response = await fetchWithTimeout("/api/chat", input, input.signal);
  if (!response.ok) throw new ChatApiError(parseProblem(response.status));
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw invalidResponse();
  }
  return parseResponse(body);
}

function dispatchEvent(
  parsed: ParsedSseEvent,
  callbacks: ChatStreamCallbacks,
  state: { response?: ChatResponse; completed: boolean },
): void {
  if (state.completed) return;
  if (parsed.event === "started") {
    if (!isRecord(parsed.data)) throw invalidResponse();
    callbacks.onStarted?.({ conversation_id: stringField(parsed.data, "conversation_id") });
  } else if (parsed.event === "delta") {
    if (!isRecord(parsed.data)) throw invalidResponse();
    callbacks.onDelta?.({
      conversation_id: stringField(parsed.data, "conversation_id"),
      text: stringField(parsed.data, "text"),
    });
  } else if (parsed.event === "message") {
    state.response = parseResponse(parsed.data);
    callbacks.onMessage?.(state.response);
  } else if (parsed.event === "completed") {
    if (!isRecord(parsed.data) || parsed.data.stream_status !== "completed") throw invalidResponse();
    const dialogStatus = stringField(parsed.data, "dialog_status");
    if (!DIALOG_STATUSES.has(dialogStatus as DialogStatus)) throw invalidResponse();
    state.completed = true;
    callbacks.onCompleted?.({
      conversation_id: stringField(parsed.data, "conversation_id"),
      stream_status: "completed",
      dialog_status: dialogStatus as DialogStatus,
    });
  } else if (parsed.event === "error") {
    const message = isRecord(parsed.data) && typeof parsed.data.message === "string"
      ? parsed.data.message
      : "Hệ thống chưa thể xử lý yêu cầu.";
    throw new ChatApiError({ code: "backend_internal_error", detail: message });
  }
}

export async function streamChat(
  input: ChatRequest & { signal?: AbortSignal },
  callbacks: ChatStreamCallbacks = {},
): Promise<ChatResponse> {
  const response = await fetchWithTimeout("/api/chat/stream", input, input.signal);
  if (!response.ok) throw new ChatApiError(parseProblem(response.status));
  if (!response.body) throw invalidResponse();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  const state: { response?: ChatResponse; completed: boolean } = { completed: false };
  const cancelReader = () => {
    void reader.cancel();
  };
  input.signal?.addEventListener("abort", cancelReader, { once: true });
  try {
    while (true) {
      if (input.signal?.aborted) throw cancelledRequest();
      let chunk: ReadableStreamReadResult<Uint8Array>;
      try {
        chunk = await reader.read();
      } catch {
        if (input.signal?.aborted) throw cancelledRequest();
        throw new ChatApiError({
          code: "stream_interrupted",
          detail: "Kết nối bị gián đoạn; trạng thái booking có thể chưa chắc chắn. Không tự động gửi lại.",
        });
      }
      const { value, done } = chunk;
      if (input.signal?.aborted) throw cancelledRequest();
      for (const event of parser.feed(decoder.decode(value, { stream: !done }))) {
        if (input.signal?.aborted) throw cancelledRequest();
        dispatchEvent(event, callbacks, state);
      }
      if (done) break;
    }
  } finally {
    input.signal?.removeEventListener("abort", cancelReader);
  }
  if (input.signal?.aborted) throw cancelledRequest();
  if (parser.hasPendingData() || !state.completed || !state.response) {
    throw new ChatApiError({
      code: "stream_interrupted",
      detail: "Kết nối bị gián đoạn; trạng thái booking có thể chưa chắc chắn. Không tự động gửi lại.",
    });
  }
  return state.response;
}
