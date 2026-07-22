"use client";

import { Eye } from "lucide-react";
import { absoluteMinutesToHHMM, durationToWidth, timeToX, type TimeRange } from "./schedule.utils";
import { MIN_BOOKING_WIDTH } from "./schedule.theme";
import type { BookingViewModel } from "./schedule.types";

interface CancelledBookingLayerProps {
  bookings: BookingViewModel[];
  range: TimeRange;
  pxPerMinute: number;
  onSelect: (booking: BookingViewModel) => void;
}

// Render booking đã hủy ở lớp nền không chặn selection, chỉ nút chi tiết nhận sự kiện click.
export function CancelledBookingLayer({
  bookings,
  range,
  pxPerMinute,
  onSelect,
}: CancelledBookingLayerProps) {
  return (
    <div className="pointer-events-none absolute inset-0 z-[1]" data-layer="cancelled-bookings">
      {bookings.map((booking) => {
        const x = timeToX(booking.startMinutes, range, pxPerMinute);
        const width = durationToWidth(booking.endMinutes - booking.startMinutes, pxPerMinute);
        const narrow = width < 92;
        return (
          <div
            key={booking.reservationId}
            data-booking-status="cancelled"
            className="pointer-events-none absolute overflow-hidden rounded border border-dashed border-red-300 bg-red-50/70 opacity-60"
            style={{ left: x, width: Math.max(width, MIN_BOOKING_WIDTH), top: 3, bottom: 3 }}
            title={`${booking.customerName ?? booking.customerPhone} · Đã hủy`}
          >
            <div className="flex h-full flex-col justify-center px-1.5 pr-7 text-red-800 line-through">
              <span className="truncate text-[11px] font-semibold">
                {booking.customerName ?? booking.customerPhone}
              </span>
              <span className="truncate text-[10px] font-medium">
                Đã hủy{!narrow ? ` · ${absoluteMinutesToHHMM(booking.startMinutes)}–${absoluteMinutesToHHMM(booking.endMinutes)}` : ""}
              </span>
            </div>
            <button
              type="button"
              className="pointer-events-auto absolute right-1 top-1/2 z-[1] flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded border border-red-200 bg-white/90 text-red-700 shadow-sm hover:bg-white focus:outline-none focus:ring-2 focus:ring-red-300"
              aria-label={`Xem booking đã hủy của ${booking.customerName ?? booking.customerPhone}`}
              title="Xem chi tiết booking đã hủy"
              onClick={(event) => {
                event.stopPropagation();
                onSelect(booking);
              }}
            >
              <Eye className="h-3 w-3" aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
