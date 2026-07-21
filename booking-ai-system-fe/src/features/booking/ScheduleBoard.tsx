"use client";

import { useState } from "react";
import { ScheduleHeader } from "./ScheduleHeader";
import { ResourceRow } from "./ResourceRow";
import { CurrentTimeLine } from "./CurrentTimeLine";
import { type Selection } from "./SelectionLayer";
import type { BookingViewModel, ScheduleViewModel } from "./schedule.types";
import type { TimeStep } from "./schedule.theme";
import { RESOURCE_COLUMN_WIDTH, PX_PER_MINUTE } from "./schedule.theme";
import { SHOP_TIMEZONE } from "@/shared/config/shop";

interface ScheduleBoardProps {
  schedule: ScheduleViewModel | undefined;
  isLoading: boolean;
  isError: boolean;
  error?: Error;
  step: TimeStep;
  onSelectBooking: (b: BookingViewModel) => void;
  onCreateBooking: (selection: Selection) => void;
}

// Bảng timeline chính. Quản lý selection cục bộ (không context lớn — nguyên tắc 5).
export function ScheduleBoard({
  schedule,
  isLoading,
  isError,
  error,
  step,
  onSelectBooking,
  onCreateBooking,
}: ScheduleBoardProps) {
  const [selection, setSelection] = useState<Selection | null>(null);

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-zinc-500">
        Đang tải lịch...
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex h-64 items-center justify-center text-red-600">
        Lỗi tải lịch: {error?.message ?? "Không xác định"}
      </div>
    );
  }
  if (!schedule || schedule.resources.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-zinc-500">
        Không có therapist/ca nào cho ngày này.
      </div>
    );
  }

  const range = {
    start: schedule.timelineStartMinutes,
    end: schedule.timelineEndMinutes,
  };
  const totalWidth = (range.end - range.start) * PX_PER_MINUTE;

  return (
    <div className="overflow-auto border border-zinc-200 rounded-lg">
      <div style={{ minWidth: RESOURCE_COLUMN_WIDTH + totalWidth }}>
        <ScheduleHeader range={range} step={step} />
        <div className="relative">
          {schedule.resources.map((res) => (
            <ResourceRow
              key={res.therapistId}
              resource={res}
              bookings={schedule.bookings.filter((b) => b.therapistId === res.therapistId)}
              range={range}
              step={step}
              selection={selection}
              onSelectBooking={onSelectBooking}
              onStartSelection={setSelection}
              onCommitSelection={(sel) => {
                onCreateBooking(sel);
                setSelection(null);
              }}
              onClearSelection={() => setSelection(null)}
            />
          ))}
          <CurrentTimeLine
            range={range}
            date={schedule.date}
            timezone={SHOP_TIMEZONE}
          />
        </div>
      </div>
    </div>
  );
}
