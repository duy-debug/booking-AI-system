import { RESOURCE_COLUMN_WIDTH, ROW_HEIGHT } from "./schedule.theme";

interface ResourceColumnProps {
  name: string;
}

// Cột therapist — sticky trái (nguyên tắc 7).
export function ResourceColumn({ name }: ResourceColumnProps) {
  return (
    <div
      className="sticky left-0 z-20 flex shrink-0 items-center border-r border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-800"
      style={{ width: RESOURCE_COLUMN_WIDTH, height: ROW_HEIGHT }}
    >
      <span className="truncate">{name}</span>
    </div>
  );
}
