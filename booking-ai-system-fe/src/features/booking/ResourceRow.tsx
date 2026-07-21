"use client";

import { useRef } from "react";
import type { TimeRange } from "./schedule.utils";
import { xToMinutes, snapMinutes } from "./schedule.utils";
import { PX_PER_MINUTE, ROW_HEIGHT, type TimeStep } from "./schedule.theme";
import { ResourceColumn } from "./ResourceColumn";
import { ShiftLayer } from "./ShiftLayer";
import { BookingLayer } from "./BookingLayer";
import { SelectionLayer, type Selection } from "./SelectionLayer";
import { TimeGrid } from "./TimeGrid";
import type { BookingViewModel, ResourceViewModel } from "./schedule.types";

interface ResourceRowProps {
  resource: ResourceViewModel;
  bookings: BookingViewModel[];
  range: TimeRange;
  step: TimeStep;
  selection: Selection | null;
  onSelectBooking: (b: BookingViewModel) => void;
  onStartSelection: (sel: Selection) => void;
  onCommitSelection: (sel: Selection) => void;
  onClearSelection: () => void;
}

// Một dòng resource: cột tên + track chứa các layer.
export function ResourceRow({
  resource,
  bookings,
  range,
  step,
  selection,
  onSelectBooking,
  onStartSelection,
  onCommitSelection,
  onClearSelection,
}: ResourceRowProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const totalWidth = (range.end - range.start) * PX_PER_MINUTE;

  const handleClick = (e: React.MouseEvent) => {
    if (!trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const absMin = snapMinutes(xToMinutes(x, range, PX_PER_MINUTE), step);
    const end = Math.min(absMin + step * 2, range.end);
    onStartSelection({ startMinutes: absMin, endMinutes: end, therapistId: resource.therapistId });
  };

  return (
    <div className="flex border-b border-zinc-100" style={{ height: ROW_HEIGHT }}>
      <ResourceColumn name={resource.name} />
      <div
        ref={trackRef}
        className="relative cursor-pointer bg-white"
        style={{ width: totalWidth }}
        onClick={handleClick}
      >
        <TimeGrid range={range} height={ROW_HEIGHT} />
        <ShiftLayer shifts={resource.shifts} range={range} />
        <BookingLayer bookings={bookings} range={range} onSelect={onSelectBooking} />
        <SelectionLayer
          selection={selection}
          range={range}
          onCommit={onCommitSelection}
          onClear={onClearSelection}
        />
      </div>
    </div>
  );
}
