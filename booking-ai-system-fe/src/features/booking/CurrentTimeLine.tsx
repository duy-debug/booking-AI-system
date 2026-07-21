"use client";

import { useEffect, useState } from "react";
import { nowAbsoluteMinutes, timeToX, type TimeRange } from "./schedule.utils";
import { PX_PER_MINUTE, RESOURCE_COLUMN_WIDTH, HEADER_HEIGHT } from "./schedule.theme";

interface CurrentTimeLineProps {
  range: TimeRange;
  date: string;
  timezone: string;
}

// Đường dọc biểu diễn thời gian hiện tại. Tự cập nhật mỗi phút.
export function CurrentTimeLine({ range, date, timezone }: CurrentTimeLineProps) {
  const [x, setX] = useState<number | null>(null);

  useEffect(() => {
    const update = () => setX(nowAbsoluteMinutes(range, date, timezone));
    update();
    const t = setInterval(update, 60_000);
    return () => clearInterval(t);
  }, [range, date, timezone]);

  if (x === null) return null;
  return (
    <div
      className="pointer-events-none absolute top-0 z-20"
      style={{ left: RESOURCE_COLUMN_WIDTH + timeToX(x, range, PX_PER_MINUTE), height: `calc(100% - 0px)` }}
    >
      <div className="h-full w-px bg-red-500" />
      <div className="absolute -left-1 -top-0 h-2 w-2 rounded-full bg-red-500" style={{ top: HEADER_HEIGHT - 8 }} />
    </div>
  );
}
