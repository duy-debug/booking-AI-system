"use client";

import { useEffect, useState } from "react";
import { nowAbsoluteMinutes, timeToX, type TimeRange } from "./schedule.utils";
import { RESOURCE_COLUMN_WIDTH } from "./schedule.theme";

interface CurrentTimeLineProps {
  range: TimeRange;
  date: string;
  timezone: string;
  pxPerMinute: number;
}

// Hiển thị đường thời gian hiện tại khi ngày được chọn là hôm nay và cập nhật vị trí mỗi phút theo múi giờ của shop.
export function CurrentTimeLine({ range, date, timezone, pxPerMinute }: CurrentTimeLineProps) {
  const [x, setX] = useState<number | null>(null);

  useEffect(() => {
    // Tính lại tọa độ thời gian hiện tại để đường đỏ dịch chuyển theo đồng hồ thực.
    const update = () => setX(nowAbsoluteMinutes(range, date, timezone));
    update();
    const t = setInterval(update, 60_000);
    return () => clearInterval(t);
  }, [range, date, timezone]);

  if (x === null) return null;

  const left = RESOURCE_COLUMN_WIDTH + timeToX(x, range, pxPerMinute);

  return (
    <div
      className="pointer-events-none absolute top-0 z-[4]"
      style={{ left }}
    >
      <div className="h-full w-0.5 bg-red-500 shadow-[0_0_4px_rgba(239,68,68,0.5)]" />
      <div className="absolute -left-1 top-0 w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_4px_rgba(239,68,68,0.5)]" />
    </div>
  );
}
