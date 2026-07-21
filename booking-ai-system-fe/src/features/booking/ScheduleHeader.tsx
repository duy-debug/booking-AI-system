import { formatAbsoluteHour, type TimeRange } from "./schedule.utils";
import { PX_PER_MINUTE, RESOURCE_COLUMN_WIDTH, HEADER_HEIGHT, type TimeStep } from "./schedule.theme";

interface ScheduleHeaderProps {
  range: TimeRange;
  step: TimeStep;
}

// Header thời gian — sticky top. Phải lùi sang phải bằng độ rộng cột resource.
export function ScheduleHeader({ range, step }: ScheduleHeaderProps) {
  const ticks: number[] = [];
  for (let t = range.start; t <= range.end; t += step) ticks.push(t);

  const totalWidth = (range.end - range.start) * PX_PER_MINUTE;

  return (
    <div
      className="sticky top-0 z-30 flex bg-white"
      style={{ height: HEADER_HEIGHT }}
    >
      <div
        className="sticky left-0 z-40 shrink-0 border-r border-zinc-200 bg-white"
        style={{ width: RESOURCE_COLUMN_WIDTH }}
      />
      <div className="relative" style={{ width: totalWidth }}>
        {ticks.map((t) => (
          <div
            key={t}
            className="absolute top-0 flex h-full items-center border-l border-zinc-200 pl-1 text-xs text-zinc-500"
            style={{ left: (t - range.start) * PX_PER_MINUTE }}
          >
            {formatAbsoluteHour(t, { padDay: true })}
          </div>
        ))}
      </div>
    </div>
  );
}
