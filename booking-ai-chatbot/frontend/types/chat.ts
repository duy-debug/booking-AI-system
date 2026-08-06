export type BookingState =
  | "idle" | "selecting_shop" | "selecting_date" | "selecting_people"
  | "selecting_duration" | "selecting_service" | "selecting_time"
  | "selecting_therapist" | "collecting_phone" | "collecting_name"
  | "verifying_phone" | "awaiting_confirmation" | "booking_executing"
  | "completed" | "booking_failed" | "cancelled";

export type DialogStatus = "success" | "failure_handled" | "failure_unhandled";
export type SafeMetadataValue = boolean | number | string | null;

export interface ChatRequest {
  conversation_id: string;
  message: string;
}

export interface ChatResponse {
  conversation_id: string;
  text: string;
  state: BookingState;
  status: DialogStatus;
  instruction_template: string | null;
  quick_replies: string[];
  metadata: Record<string, SafeMetadataValue>;
}

export interface ChatStartedEvent { conversation_id: string }
export interface ChatCompletedEvent {
  conversation_id: string;
  stream_status: "completed";
  dialog_status: DialogStatus;
}
export interface ChatErrorEvent { conversation_id: string; code: string; message: string }

export type ChatErrorCode =
  | "network_error" | "timeout" | "invalid_response" | "stream_interrupted"
  | "backend_validation_error" | "backend_internal_error" | "cancelled";

export interface ChatProblem { status?: number; code: ChatErrorCode; detail: string }

export interface ChatMessage {
  id: string;
  role: "assistant" | "user" | "system";
  text: string;
  response?: ChatResponse;
  createdAt: number;
  status?: "sending" | "sent" | "failed";
}
