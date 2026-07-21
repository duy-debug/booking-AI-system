import { timeToX, durationToWidth, type TimeRange } from "./schedule.utils";
import { PX_PER_MINUTE } from "./schedule.theme";
import type { ShiftViewModel } from "./schedule.types";

interface ShiftLayerProps {
  shifts: ShiftViewModel[];
  range: TimeRange;
}

// Lớp nền: vẽ ca làm việc của resource này.
export function ShiftLayer({ shifts, range }: ShiftLayerProps) {
  return (
    <div className="pointer-events-none absolute inset-0">
      {shifts.map((s) => {
        const x = timeToX(s.startMinutes, range, PX_PER_MINUTE);
        const w = durationToWidth(s.endMinutes - s.startMinutes, PX_PER_MINUTE);
        return (
          <div
            key={s.id}
            className={`absolute top-0 h-full rounded-md ${
              s.isActive ? "bg-emerald-50" : "bg-zinc-100"
            } border border-emerald-200`}
            style={{ left: x, width: w }}
          />
        );
      })}
    </div>
  );
}
