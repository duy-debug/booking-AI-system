"use client";

import { useState, useCallback, useMemo, useRef, useEffect } from "react";
import { ScheduleHeader } from "./ScheduleHeader";
import { ResourceRow } from "./ResourceRow";
import { CurrentTimeLine } from "./CurrentTimeLine";
import { type Selection } from "./SelectionLayer";
import type { BookingViewModel, ScheduleViewModel } from "./schedule.types";
import {
  RESOURCE_COLUMN_WIDTH,
} from "./schedule.theme";
import {
  calculatePixelsPerMinute,
  FIT_BREAKPOINT,
  MOBILE_PX_PER_MINUTE,
} from "./schedule.utils";
import { todayShopDate } from "@/shared/lib/datetime";
import { earliestSelectableForDate, validateBookingStart } from "./booking-time";
import { useAlert } from "@/shared/components/AlertProvider";

interface ScheduleBoardProps {
  schedule: ScheduleViewModel | undefined;
  isLoading: boolean;
  isError: boolean;
  error?: Error;
  onSelectBooking: (b: BookingViewModel) => void;
  onCreateBooking: (selection: Selection) => void;
}

// Tính tỉ lệ timeline, quản lý selection và render toàn bộ resource rows của lịch trong ngày.
export function ScheduleBoard({
  schedule,
  isLoading,
  isError,
  error,
  onSelectBooking,
  onCreateBooking,
}: ScheduleBoardProps) {
  const { showError } = useAlert();
  const [selection, setSelection] = useState<Selection | null>(null);
  const boardRef = useRef<HTMLDivElement>(null);
  const [boardWidth, setBoardWidth] = useState(0);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    // Cập nhật đồng hồ định kỳ để vùng không được chọn tiến theo thời gian thực.
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  // Xóa selection khi chuyển ngày để không giữ lại khung giờ của lịch cũ.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelection(null);
  }, [schedule?.date]);

  // ResizeObserver on the board container (entire width)
  useEffect(() => {
    const el = boardRef.current;
    if (!el) return;
    // Theo dõi chiều rộng board để chuyển giữa chế độ fit desktop và cuộn ngang mobile.
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setBoardWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Xóa selection hiện tại khi người dùng hủy hoặc chuyển sang vùng khác.
  const handleClearSelection = useCallback(() => setSelection(null), []);
  // Ghi nhận selection bước đầu để layer hiển thị khoảng giờ đang chọn.
  const handleStartSelection = useCallback((sel: Selection) => {
    setSelection(sel);
  }, []);
  // Xác thực giới hạn đặt trước rồi mở form tạo booking hoặc hiển thị alert lỗi thời gian.
  const handleCommitSelection = useCallback((sel: Selection) => {
    if (!schedule) return;
    const validation = validateBookingStart({
      bookingDate: schedule.date,
      startMinutes: sel.startMinutes,
      timeZone: schedule.timezone,
      now: new Date(),
      advanceMinutes: schedule.minimumBookingAdvanceMinutes,
    });
    if (!validation.valid) {
      setSelection(null);
      showError(validation.message ?? "Thời gian bắt đầu không hợp lệ.");
      return;
    }
    onCreateBooking(sel);
    setSelection(null);
  }, [onCreateBooking, schedule, showError]);

  // Nhóm booking theo therapist một lần để mỗi ResourceRow chỉ nhận dữ liệu liên quan.
  const bookingsByTherapist = useMemo(() => {
    if (!schedule) return new Map<string, BookingViewModel[]>();
    const map = new Map<string, BookingViewModel[]>();
    for (const b of schedule.bookings) {
      const arr = map.get(b.therapistId);
      if (arr) arr.push(b);
      else map.set(b.therapistId, [b]);
    }
    return map;
  }, [schedule]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-400 text-sm">
        Đang tải lịch...
      </div>
    );
  }
  if (isError) {
    return (
      <div className="flex h-full items-center justify-center text-red-500 text-sm">
        Lỗi: {error?.message ?? "Không xác định"}
      </div>
    );
  }
  if (!schedule || schedule.resources.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-zinc-400 text-sm">
        Không có therapist/ca nào cho ngày này.
      </div>
    );
  }

  const range = {
    start: schedule.timelineStartMinutes,
    end: schedule.timelineEndMinutes,
  };
  const totalMinutes = range.end - range.start;

  // Available width for timeline = board width minus therapist column
  const availableWidth = Math.max(0, boardWidth - RESOURCE_COLUMN_WIDTH);
  const isDesktop = boardWidth >= FIT_BREAKPOINT;

  // Desktop: fit exactly (availableWidth / totalMinutes) → no overflow
  // Mobile: fixed minimum PPM → overflow-x-auto
  const pxPerMinute = availableWidth > 0
    ? isDesktop
      ? calculatePixelsPerMinute(availableWidth, totalMinutes)
      : MOBILE_PX_PER_MINUTE
    : 1.0;

  const isToday = schedule.date === todayShopDate(schedule.timezone);
  const earliestSelectableMinutes = earliestSelectableForDate({
    bookingDate: schedule.date,
    timeZone: schedule.timezone,
    now,
    advanceMinutes: schedule.minimumBookingAdvanceMinutes,
  });

  return (
    <div
      ref={boardRef}
      className={`h-full min-h-0 rounded-lg border border-zinc-200 bg-white ${
        isDesktop
          ? "overflow-x-hidden overflow-y-auto"
          : "overflow-auto"
      }`}
    >
      <ScheduleHeader range={range} pxPerMinute={pxPerMinute} />
      {/* Each ResourceRow has its own ResourceColumn + timeline */}
      <div className="relative">
        {schedule.resources.map((res) => (
          <ResourceRow
            key={res.therapistId}
            resource={res}
            bookings={bookingsByTherapist.get(res.therapistId) ?? []}
            range={range}
            pxPerMinute={pxPerMinute}
            selection={selection}
            onSelectBooking={onSelectBooking}
            onStartSelection={handleStartSelection}
            onCommitSelection={handleCommitSelection}
            onClearSelection={handleClearSelection}
            earliestSelectableMinutes={earliestSelectableMinutes}
            breakMinutes={schedule.therapistBreakMinutes}
            onInvalidSelection={() => showError(
              earliestSelectableMinutes === Number.POSITIVE_INFINITY
                ? "Không thể tạo booking cho ngày trong quá khứ."
                : `Booking phải bắt đầu sau ít nhất ${schedule.minimumBookingAdvanceMinutes} phút.`,
            )}
          />
        ))}
        {isToday && (
          <CurrentTimeLine
            range={range}
            date={schedule.date}
            timezone={schedule.timezone}
            pxPerMinute={pxPerMinute}
          />
        )}
      </div>
    </div>
  );
}
