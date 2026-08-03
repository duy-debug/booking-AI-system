export interface ChatRequest {
  conversation_id: string;
  message: string;
  idempotency_key?: string | null;
}

export interface ChatResponse {
  conversation_id: string;
  text: string;
  state: string;
  status: string;
  instruction_template: string | null;
  quick_replies: string[];
  metadata: Record<string, unknown>;
}

export interface ChatStartedEvent {
  conversation_id: string;
}

export interface ChatCompletedEvent {
  conversation_id: string;
  stream_status: "completed";
  dialog_status: string;
}

export interface ChatErrorEvent {
  conversation_id: string;
  code: string;
  message: string;
}

export interface ChatProblem {
  status?: number;
  code: string;
  detail: string;
}

export interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  text: string;
  response?: ChatResponse;
  createdAt: number;
}
