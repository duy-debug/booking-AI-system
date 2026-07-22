"use client";

import { useCallback } from "react";
import { timeToX, durationToWidth, absoluteMinutesToHHMM, type TimeRange } from "./schedule.utils";
import { MIN_SELECTION_WIDTH } from "./schedule.theme";

export interface Selection {
  startMinutes: number;
  endMinutes: number;
  therapistId?: string;
}

interface SelectionLayerProps {
  selection: Selection | null;
  range: TimeRange;
  pxPerMinute: number;
  onCommit: (selection: Selection) => void;
  onClear: () => void;
}

// Hiển thị vùng giờ đang chọn và phát sự kiện commit để mở form tạo booking.
export function SelectionLayer({
  selection,
  range,
  pxPerMinute,
  onCommit,
  onClear,
}: SelectionLayerProps) {
  // Xác nhận vùng selection hiện tại để cha mở luồng tạo booking.
  const handleCommit = useCallback(() => {
    if (selection) onCommit(selection);
  }, [selection, onCommit]);
  // Xóa selection mà không tạo booking khi người dùng hủy vùng đã chọn.
  const handleClear = useCallback(() => onClear(), [onClear]);

  if (!selection) return null;

  const x = timeToX(selection.startMinutes, range, pxPerMinute);
  const w = durationToWidth(selection.endMinutes - selection.startMinutes, pxPerMinute);
  const label = `${absoluteMinutesToHHMM(selection.startMinutes)}–${absoluteMinutesToHHMM(selection.endMinutes)}`;

  return (
    <button
      type="button"
      title={`Tạo booking: ${label}`}
      aria-label={`Tạo booking khung ${label}`}
      onClick={handleCommit}
      onDoubleClick={handleClear}
      onKeyDown={(e) => { if (e.key === "Delete" || e.key === "Escape") handleClear(); }}
      className="absolute z-[3] rounded border-2 border-dashed border-blue-500 bg-blue-100/60 hover:bg-blue-100/80 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors cursor-pointer"
      style={{ left: x, width: Math.max(w, MIN_SELECTION_WIDTH), top: 4, bottom: 4 }}
    >
      <span className="absolute top-0 left-1 text-[10px] text-blue-700 font-medium whitespace-nowrap pointer-events-none">
        {label}
      </span>
    </button>
  );
}
