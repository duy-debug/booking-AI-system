import { RESOURCE_COLUMN_WIDTH, ROW_HEIGHT } from "./schedule.theme";

interface ResourceColumnProps {
  name: string;
  hasActiveShift: boolean;
  hasAnyShift: boolean;
}

// Hiển thị tên therapist và trạng thái ca làm trong cột resource cố định của timeline.
export function ResourceColumn({ name, hasActiveShift, hasAnyShift }: ResourceColumnProps) {
  let statusDot: string;
  let statusLabel: string;

  if (hasActiveShift) {
    statusDot = "bg-emerald-500";
    statusLabel = "Đang làm";
  } else if (hasAnyShift) {
    statusDot = "bg-zinc-300";
    statusLabel = "Ca không hoạt động";
  } else {
    statusDot = "bg-red-300";
    statusLabel = "Không có ca";
  }

  return (
    <div
      className="sticky left-0 z-20 flex shrink-0 items-center gap-2 border-r border-zinc-200 bg-white px-2"
      style={{ width: RESOURCE_COLUMN_WIDTH, height: ROW_HEIGHT }}
    >
      <span
        className={`inline-block w-2 h-2 rounded-full shrink-0 ${statusDot}`}
        title={statusLabel}
        aria-label={statusLabel}
      />
      <span className="truncate text-sm font-medium text-zinc-800">{name}</span>
    </div>
  );
}
