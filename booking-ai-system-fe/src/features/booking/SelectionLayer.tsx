import { timeToX, durationToWidth, type TimeRange } from "./schedule.utils";
import { PX_PER_MINUTE } from "./schedule.theme";

export interface Selection {
  startMinutes: number;
  endMinutes: number;
  therapistId?: string;
}

interface SelectionLayerProps {
  selection: Selection | null;
  range: TimeRange;
  onCommit: (selection: Selection) => void;
  onClear: () => void;
}

// Lớp chọn: block mờ khi user kéo/chọn ô trống để tạo booking.
export function SelectionLayer({
  selection,
  range,
  onCommit,
  onClear,
}: SelectionLayerProps) {
  if (!selection) return null;
  const x = timeToX(selection.startMinutes, range, PX_PER_MINUTE);
  const w = durationToWidth(selection.endMinutes - selection.startMinutes, PX_PER_MINUTE);
  return (
    <button
      type="button"
      title="Nhấn để tạo booking"
      onClick={() => onCommit(selection)}
      onDoubleClick={onClear}
      className="absolute top-1.5 bottom-1.5 rounded-md border-2 border-dashed border-blue-400 bg-blue-100/60"
      style={{ left: x, width: Math.max(w, 40) }}
    />
  );
}
