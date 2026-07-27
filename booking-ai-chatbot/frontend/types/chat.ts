export type UiType =
  | "text" | "shop_options" | "course_options" | "addon_options"
  | "people_options" | "date_picker" | "slot_options"
  | "therapist_request_options" | "therapist_options" | "gender_options"
  | "customer_form" | "booking_summary" | "confirmation" | "booking_result"
  | "booking_lookup_form" | "booking_detail" | "booking_cancel_form"
  | "booking_cancel_summary" | "booking_update_form" | "booking_update_summary";

export interface UiOption {
  id: string;
  label: string;
  description?: string | null;
  metadata: Record<string, unknown>;
}

export interface UiBlock {
  type: UiType;
  options: UiOption[];
  data: Record<string, unknown>;
}

export interface ChatSelection {
  entity: string;
  value: unknown;
  label?: string;
  metadata?: Record<string, unknown>;
}

export interface ChatResponse {
  contract_version: "1.0";
  answer: string;
  intent: string;
  conversation_id: string;
  data?: unknown;
  missing_entities?: string[];
  ui?: UiBlock | null;
}

export interface ProblemDetails {
  status: number;
  code: string;
  detail: string;
  errors?: Array<{ field: string; message: string }>;
}

export interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  text: string;
  response?: ChatResponse;
  createdAt: number;
}
