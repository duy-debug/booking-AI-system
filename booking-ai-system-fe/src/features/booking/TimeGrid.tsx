"use client";

import { buildHourTicks } from "./schedule.utils";
import type { TimeRange } from "./schedule.utils";
import { PX_PER_MINUTE } from "./schedule.theme";

interface TimeGridProps {
  range: TimeRange;
  height: number;
}

// Lưới giờ mờ phía sau các layer (nguyên tắc 9: ít nhiễu).
export function TimeGrid({ range, height }: TimeGridProps) {
  const ticks = buildHourTicks(range, PX_PER_MINUTE, { padDay: true });
  return (
    <div className="pointer-events-none absolute inset-0">
      {ticks.map((t) => (
        <div
          key={t.absoluteMinutes}
          className="absolute top-0 border-l border-zinc-100"
          style={{ left: t.x * PX_PER_MINUTE, height }}
        />
      ))}
    </div>
  );
}
