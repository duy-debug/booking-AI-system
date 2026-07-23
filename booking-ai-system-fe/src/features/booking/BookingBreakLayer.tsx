import { Fragment } from "react";
import { durationToWidth, timeToX, type TimeRange } from "./schedule.utils";
import type { BookingViewModel } from "./schedule.types";

interface BookingBreakLayerProps {
  bookings: BookingViewModel[];
  breakMinutes: number;
  range: TimeRange;
  pxPerMinute: number;
}

// Vẽ vùng nghỉ trước và sau booking active mà không làm thay đổi thời gian phục vụ khách.
export function BookingBreakLayer({
  bookings,
  breakMinutes,
  range,
  pxPerMinute,
}: BookingBreakLayerProps) {
  if (breakMinutes <= 0) return null;

  return (
    <div className="pointer-events-none absolute inset-0 z-[1]" data-layer="booking-breaks">
      {bookings
        .filter((booking) => booking.status !== "cancelled")
        .map((booking) => (
          <Fragment key={`break-${booking.reservationId}`}>
            <div
              className="absolute inset-y-1 border-x border-dashed border-amber-300 bg-amber-100/70"
              style={{
                left: timeToX(
                  Math.max(range.start, booking.startMinutes - breakMinutes),
                  range,
                  pxPerMinute,
                ),
                width: durationToWidth(
                  Math.max(
                    0,
                    Math.min(breakMinutes, booking.startMinutes - range.start),
                  ),
                  pxPerMinute,
                ),
              }}
              aria-hidden="true"
            />
            <div
              className="absolute inset-y-1 border-x border-dashed border-amber-300 bg-amber-100/70"
              style={{
                left: timeToX(booking.endMinutes, range, pxPerMinute),
                width: durationToWidth(
                  Math.max(
                    0,
                    Math.min(breakMinutes, range.end - booking.endMinutes),
                  ),
                  pxPerMinute,
                ),
              }}
              aria-hidden="true"
            />
          </Fragment>
        ))}
    </div>
  );
}
