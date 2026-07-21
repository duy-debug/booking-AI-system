import type { BookingStatusToken } from "./schedule.types";

// Cấu hình timeline — tách khỏi component (nguyên tắc 5).
export const PX_PER_MINUTE = 4; // 1 giờ = 240px
export const RESOURCE_COLUMN_WIDTH = 200; // px cột therapist (sticky)
export const HEADER_HEIGHT = 48;
export const ROW_HEIGHT = 64;

export const TIME_STEPS = [5, 10, 15, 30] as const;
export type TimeStep = (typeof TIME_STEPS)[number];

// Màu booking theo status token (nguyên tắc 10: màu + label/tooltip, không chỉ màu)
export const STATUS_STYLES: Record<
  BookingStatusToken,
  { bg: string; border: string; label: string }
> = {
  confirmed: {
    bg: "bg-blue-100",
    border: "border-blue-400",
    label: "Đã xác nhận",
  },
  cancelled: {
    bg: "bg-zinc-200",
    border: "border-zinc-400",
    label: "Đã huỷ",
  },
  other: {
    bg: "bg-amber-100",
    border: "border-amber-400",
    label: "Khác",
  },
};
