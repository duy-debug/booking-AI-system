"use client";

import { memo, useCallback } from "react";
import { timeToX, durationToWidth, absoluteMinutesToHHMM, type TimeRange } from "./schedule.utils";
import { MIN_BOOKING_WIDTH, STATUS_STYLES } from "./schedule.theme";
import type { BookingViewModel } from "./schedule.types";

interface BookingLayerProps {
  bookings: BookingViewModel[];
  range: TimeRange;
  pxPerMinute: number;
  onSelect: (booking: BookingViewModel) => void;
}

// Render một booking active riêng lẻ, xử lý click và tối ưu re-render bằng memo.
const BookingBlock = memo(function BookingBlock({
  booking,
  x,
  w,
  style,
  onSelect,
}: {
  booking: BookingViewModel;
  x: number;
  w: number;
  style: (typeof STATUS_STYLES)[keyof typeof STATUS_STYLES];
  onSelect: (b: BookingViewModel) => void;
}) {
  // Chuyển booking hiện tại về callback selection ổn định khi người dùng mở chi tiết.
  const handleClick = useCallback(() => onSelect(booking), [booking, onSelect]);
  const narrow = w < 80;

  return (
    <button
      type="button"
      onClick={handleClick}
      title={`${booking.customerName ?? booking.customerPhone} — ${booking.courseNames.join(", ")} — ${style.label}`}
      aria-label={`Booking: ${booking.customerName ?? booking.customerPhone}, ${booking.courseNames.join(", ")}, ${absoluteMinutesToHHMM(booking.startMinutes)}-${absoluteMinutesToHHMM(booking.endMinutes)}, ${style.label}`}
      className={`pointer-events-auto absolute overflow-hidden rounded border-l-2 ${style.border} ${style.bg} hover:ring-2 hover:ring-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow cursor-pointer`}
      style={{ left: x, width: Math.max(w, MIN_BOOKING_WIDTH), top: 2, bottom: 2 }}
    >
      {narrow ? (
        <div className="flex items-center justify-center h-full px-0.5">
          <span className={`text-[10px] font-bold ${style.text} truncate`}>
            {booking.customerName?.charAt(0) ?? booking.customerPhone?.charAt(0) ?? "?"}
          </span>
        </div>
      ) : (
        <div className="px-1.5 py-0.5 h-full flex flex-col justify-center gap-0">
          <div className={`text-xs font-semibold leading-tight truncate ${style.text}`}>
            {booking.customerName ?? booking.customerPhone}
          </div>
          <div className="text-[10px] leading-tight text-zinc-600 truncate">
            {booking.courseNames.join(", ") || "—"}
          </div>
          <div className="text-[10px] leading-tight text-zinc-500">
            {absoluteMinutesToHHMM(booking.startMinutes)}–{absoluteMinutesToHHMM(booking.endMinutes)}
          </div>
        </div>
      )}
      <span className="sr-only">{style.label}</span>
    </button>
  );
});

// Render booking active thành block tương tác và định vị chúng theo phút trên timeline.
export function BookingLayer({ bookings, range, pxPerMinute, onSelect }: BookingLayerProps) {
  return (
    <div className="pointer-events-none absolute inset-0 z-[2]" data-layer="active-bookings">
      {bookings.filter((booking) => booking.status !== "cancelled").map((b) => {
        const x = timeToX(b.startMinutes, range, pxPerMinute);
        const w = durationToWidth(b.endMinutes - b.startMinutes, pxPerMinute);
        const style = STATUS_STYLES[b.status] ?? STATUS_STYLES.other;
        return (
          <BookingBlock
            key={b.reservationId}
            booking={b}
            x={x}
            w={w}
            style={style}
            onSelect={onSelect}
          />
        );
      })}
    </div>
  );
}
