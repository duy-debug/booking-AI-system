"use client";

import { useEffect, useState } from "react";
import {
  absoluteMinutesToHHMM,
  nowAbsoluteMinutes,
  timeToX,
  type TimeRange,
} from "./schedule.utils";
import { HEADER_HEIGHT, RESOURCE_COLUMN_WIDTH } from "./schedule.theme";

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
      className="pointer-events-none absolute inset-y-0 z-50"
      style={{ left }}
      aria-hidden="true"
    >
      <div
        className="absolute left-1/2 flex -translate-x-1/2 items-center rounded bg-red-500 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white shadow-sm"
        style={{ top: -HEADER_HEIGHT + 25 }}
      >
        {absoluteMinutesToHHMM(x)}
      </div>
      <div className="h-full w-px bg-red-500 shadow-[0_0_4px_rgba(239,68,68,0.45)]" />
      <div className="absolute -left-1 top-0 w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_4px_rgba(239,68,68,0.5)]" />
    </div>
  );
}
