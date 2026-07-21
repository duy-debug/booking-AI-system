import { timeToX, durationToWidth, type TimeRange } from "./schedule.utils";
import { PX_PER_MINUTE, STATUS_STYLES } from "./schedule.theme";
import type { BookingViewModel } from "./schedule.types";

interface BookingLayerProps {
  bookings: BookingViewModel[];
  range: TimeRange;
  onSelect: (booking: BookingViewModel) => void;
}

// Lớp booking: mỗi block absolute positioned từ start->end.
export function BookingLayer({ bookings, range, onSelect }: BookingLayerProps) {
  return (
    <div className="absolute inset-0">
      {bookings.map((b) => {
        const x = timeToX(b.startMinutes, range, PX_PER_MINUTE);
        const w = durationToWidth(b.endMinutes - b.startMinutes, PX_PER_MINUTE);
        const style = STATUS_STYLES[b.status];
        const title = `${b.customerName ?? b.customerPhone} — ${b.courseNames.join(", ")} (${style.label})`;
        const ariaLabel = `Đặt lịch ${b.customerName ?? b.customerPhone} — ${b.courseNames.join(", ")} — ${style.label}`;
        return (
          <button
            key={b.reservationId}
            type="button"
            title={title}
            aria-label={ariaLabel}
            onClick={() => onSelect(b)}
            className={`absolute top-1.5 bottom-1.5 overflow-hidden rounded-md border px-2 py-1 text-left text-xs ${style.bg} ${style.border} hover:ring-2 hover:ring-blue-400`}
            style={{ left: x, width: Math.max(w, 60) }}
          >
            <div className="font-medium text-zinc-900">{b.customerName ?? b.customerPhone}</div>
            <div className="truncate text-zinc-600">{b.courseNames.join(", ")}</div>
            <span className="sr-only">{style.label}</span>
          </button>
        );
      })}
    </div>
  );
}
