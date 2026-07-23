// === Layout constants ===
// PX_PER_MINUTE: default fallback khi chưa có dynamic value
export const PX_PER_MINUTE = 4;
// Clamp bounds cho dynamic pxPerMinute (24h timeline = 1440 phút)
// Desktop target: 30ph ≈ 16–36px, 1h ≈ 33–72px
export const MIN_PX_PER_MINUTE = 0.55;
export const MAX_PX_PER_MINUTE = 1.2;
export const PX_PER_MINUTE_FALLBACK = 0.8;
export const RESOURCE_COLUMN_WIDTH = 190; // px — cố định, không tham gia scale
export const HEADER_HEIGHT = 44;
export const ROW_HEIGHT = 60;

export const GRID_STEP_MINUTES = 15;
export const DEFAULT_SELECTION_DURATION_MINUTES = 15;

// === Booking status tokens ===
export type BookingStatusToken = "confirmed" | "pending" | "checked-in" | "completed" | "cancelled" | "other";

export interface StatusStyle {
  bg: string;
  border: string;
  label: string;
  text: string;
  dot: string;
}

export const STATUS_STYLES: Record<BookingStatusToken, StatusStyle> = {
  confirmed: {
    bg: "bg-blue-50",
    border: "border-blue-500",
    label: "Đã xác nhận",
    text: "text-blue-900",
    dot: "bg-blue-500",
  },
  pending: {
    bg: "bg-amber-50",
    border: "border-amber-500",
    label: "Chờ xử lý",
    text: "text-amber-900",
    dot: "bg-amber-500",
  },
  "checked-in": {
    bg: "bg-emerald-50",
    border: "border-emerald-500",
    label: "Đã check-in",
    text: "text-emerald-900",
    dot: "bg-emerald-500",
  },
  completed: {
    bg: "bg-zinc-100",
    border: "border-zinc-400",
    label: "Hoàn thành",
    text: "text-zinc-800",
    dot: "bg-zinc-500",
  },
  cancelled: {
    bg: "bg-red-50",
    border: "border-red-300",
    label: "Đã huỷ",
    text: "text-red-800 line-through",
    dot: "bg-red-400",
  },
  other: {
    bg: "bg-zinc-50",
    border: "border-zinc-300",
    label: "Khác",
    text: "text-zinc-700",
    dot: "bg-zinc-400",
  },
};

// === Zone / background tokens ===
export interface ZoneStyle {
  bg: string;
  border: string;
  pattern?: string;
}

export const ZONE_STYLES = {
  shift: {
    bg: "bg-emerald-50/40",
    border: "border-emerald-200/60",
  },
  shiftInactive: {
    bg: "bg-zinc-50",
    border: "border-zinc-200",
  },
  unavailable: {
    bg: "bg-zinc-100",
    border: "border-zinc-300",
    pattern: "diagonal-stripe",
  },
  blocked: {
    bg: "bg-red-50/50",
    border: "border-red-200",
    pattern: "diagonal-stripe",
  },
  selection: {
    bg: "bg-blue-100/70",
    border: "border-blue-500",
  },
} satisfies Record<string, ZoneStyle>;

// === Booking block sizing (min width in px) ===
export const MIN_BOOKING_WIDTH = 32;
// === Selection min width ===
export const MIN_SELECTION_WIDTH = 24;
