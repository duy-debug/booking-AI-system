"use client";

import { useRef, useCallback, memo } from "react";
import type { TimeRange } from "./schedule.utils";
import { xToMinutes, createDefaultSelection } from "./schedule.utils";
import { ROW_HEIGHT, type TimeStep } from "./schedule.theme";
import { ResourceColumn } from "./ResourceColumn";
import { ShiftLayer } from "./ShiftLayer";
import { BookingLayer } from "./BookingLayer";
import { CancelledBookingLayer } from "./CancelledBookingLayer";
import { SelectionLayer, type Selection } from "./SelectionLayer";
import { TimeGrid } from "./TimeGrid";
import type { BookingViewModel, ResourceViewModel } from "./schedule.types";

interface ResourceRowProps {
  resource: ResourceViewModel;
  bookings: BookingViewModel[];
  range: TimeRange;
  step: TimeStep;
  pxPerMinute: number;
  selection: Selection | null;
  onSelectBooking: (b: BookingViewModel) => void;
  onStartSelection: (sel: Selection) => void;
  onCommitSelection: (sel: Selection) => void;
  onClearSelection: () => void;
  earliestSelectableMinutes: number | null;
  onInvalidSelection: () => void;
}

// Tách booking cancelled khỏi booking active để render đúng layer và quy tắc pointer-event.
export function splitBookingsByCancellation(bookings: BookingViewModel[]) {
  return {
    cancelled: bookings.filter((booking) => booking.status === "cancelled"),
    active: bookings.filter((booking) => booking.status !== "cancelled"),
  };
}

// Kiểm tra một phút có nằm trong booking active và phải chặn selection hay không.
export function isMinuteBlockedByBooking(
  bookings: BookingViewModel[],
  minute: number,
) {
  return bookings.some(
    (booking) =>
      booking.status !== "cancelled" &&
      minute >= booking.startMinutes &&
      minute < booking.endMinutes,
  );
}

// Kiểm tra khoảng selection có giao với bất kỳ booking active nào của therapist hiện tại không.
export function doesSelectionOverlapActiveBooking(
  bookings: BookingViewModel[],
  startMinutes: number,
  endMinutes: number,
) {
  return bookings.some(
    (booking) =>
      booking.status !== "cancelled" &&
      startMinutes < booking.endMinutes &&
      endMinutes > booking.startMinutes,
  );
}

// Ghép resource column và các timeline layer thành một hàng therapist, đồng thời tránh render dư thừa.
const ResourceRowInner = memo(function ResourceRowInner({
  resource,
  bookings,
  range,
  step,
  pxPerMinute,
  selection,
  onSelectBooking,
  onStartSelection,
  onCommitSelection,
  onClearSelection,
  earliestSelectableMinutes,
  onInvalidSelection,
}: ResourceRowProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const totalWidth = (range.end - range.start) * pxPerMinute;
  const bookingLayers = splitBookingsByCancellation(bookings);

  // Xác định therapist có ít nhất một ca active để hiển thị đúng trạng thái resource column.
  const hasActiveShift = resource.shifts.some((s) => s.isActive);
  const hasAnyShift = resource.shifts.length > 0;

  // Quy đổi tọa độ click thành phút/step, kiểm tra vùng bị chặn và bắt đầu hoặc commit selection.
  const handleClick = useCallback((e: React.MouseEvent) => {
    if (!trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const clickedMinutes = xToMinutes(x, range, pxPerMinute);

    if (
      earliestSelectableMinutes !== null &&
      clickedMinutes < earliestSelectableMinutes
    ) {
      onInvalidSelection();
      return;
    }

    // Only create selection if clicked within an active shift
    const inActiveShift = resource.shifts.some(
      (s) => s.isActive && clickedMinutes >= s.startMinutes && clickedMinutes < s.endMinutes,
    );
    if (!inActiveShift) return;

    const sel = createDefaultSelection(clickedMinutes, step, range.end, resource.therapistId);
    if (doesSelectionOverlapActiveBooking(bookings, sel.startMinutes, sel.endMinutes)) return;
    onStartSelection(sel);
  }, [range, step, pxPerMinute, resource.therapistId, onStartSelection, resource.shifts, bookings, earliestSelectableMinutes, onInvalidSelection]);

  const rowSelection = selection?.therapistId === resource.therapistId ? selection : null;

  return (
    <div className="flex border-b border-zinc-100" style={{ height: ROW_HEIGHT }}>
      <ResourceColumn name={resource.name} hasActiveShift={hasActiveShift} hasAnyShift={hasAnyShift} />
      <div
        ref={trackRef}
        className="relative cursor-pointer bg-white"
        style={{ width: totalWidth }}
        onClick={handleClick}
        title={earliestSelectableMinutes === Number.POSITIVE_INFINITY ? "Không thể tạo booking cho ngày trong quá khứ" : undefined}
      >
        <TimeGrid range={range} height={ROW_HEIGHT} pxPerMinute={pxPerMinute} step={step} />
        <ShiftLayer shifts={resource.shifts} range={range} pxPerMinute={pxPerMinute} />
        {earliestSelectableMinutes !== null && earliestSelectableMinutes > range.start && (
          <div
            className="pointer-events-none absolute inset-y-0 left-0 border-r border-red-200 bg-zinc-400/20"
            style={{
              width: Math.min(
                totalWidth,
                (earliestSelectableMinutes - range.start) * pxPerMinute,
              ),
            }}
            aria-hidden="true"
          />
        )}
        <CancelledBookingLayer
          bookings={bookingLayers.cancelled}
          range={range}
          pxPerMinute={pxPerMinute}
          onSelect={onSelectBooking}
        />
        <BookingLayer
          bookings={bookingLayers.active}
          range={range}
          pxPerMinute={pxPerMinute}
          onSelect={onSelectBooking}
        />
        <SelectionLayer
          selection={rowSelection}
          range={range}
          pxPerMinute={pxPerMinute}
          onCommit={onCommitSelection}
          onClear={onClearSelection}
        />
      </div>
    </div>
  );
});

export { ResourceRowInner as ResourceRow };
