import { timeToX, durationToWidth, type TimeRange } from "./schedule.utils";
import type { ShiftViewModel } from "./schedule.types";

interface ShiftLayerProps {
  shifts: ShiftViewModel[];
  range: TimeRange;
  pxPerMinute: number;
}

// Vẽ các khoảng ca làm phía dưới booking để biểu diễn vùng therapist có thể phục vụ.
export function ShiftLayer({ shifts, range, pxPerMinute }: ShiftLayerProps) {
  return (
    <div className="pointer-events-none absolute inset-0 z-0" data-layer="shifts">
      {shifts.map((s) => {
        const x = timeToX(s.startMinutes, range, pxPerMinute);
        const w = durationToWidth(s.endMinutes - s.startMinutes, pxPerMinute);
        return (
          <div
            key={s.id}
            className={`absolute top-0 h-full ${
              s.isActive
                ? "bg-emerald-50/40 border-y border-emerald-200/50"
                : "bg-zinc-50 border-y border-zinc-200"
            }`}
            style={{ left: x, width: w }}
            aria-hidden
          />
        );
      })}
    </div>
  );
}
