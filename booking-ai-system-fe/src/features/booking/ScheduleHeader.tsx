import { formatAbsoluteHour, type TimeRange } from "./schedule.utils";
import { RESOURCE_COLUMN_WIDTH, HEADER_HEIGHT } from "./schedule.theme";

interface ScheduleHeaderProps {
  range: TimeRange;
  pxPerMinute: number;
}

const MIN_HOUR_LABEL_SPACING_PX = 56;

// Chọn mật độ nhãn phù hợp với tỷ lệ timeline để chữ không chồng lên nhau.
export function getHourLabelStepMinutes(pxPerMinute: number): 60 | 120 {
  return pxPerMinute * 60 >= MIN_HOUR_LABEL_SPACING_PX ? 60 : 120;
}

// Render trục thời gian phía trên với nhãn giờ khớp tuyệt đối với các resource row.
export function ScheduleHeader({ range, pxPerMinute }: ScheduleHeaderProps) {
  const totalWidth = (range.end - range.start) * pxPerMinute;
  const labelStepMinutes = getHourLabelStepMinutes(pxPerMinute);

  // Generate hour ticks (every 60 min)
  const hourTicks: { min: number; label: string }[] = [];
  for (let t = range.start; t <= range.end; t += 60) {
    hourTicks.push({ min: t, label: formatAbsoluteHour(t, { padDay: true }) });
  }

  // Generate half-hour ticks (every 60 min, offset 30)
  const halfHourTicks: number[] = [];
  for (let t = range.start + 30; t <= range.end; t += 60) {
    halfHourTicks.push(t);
  }

  return (
    <div
      className="sticky top-0 z-30 flex bg-white border-b border-zinc-200"
      style={{ height: HEADER_HEIGHT }}
    >
      <div
        className="sticky left-0 z-40 shrink-0 border-r border-zinc-200 bg-white"
        style={{ width: RESOURCE_COLUMN_WIDTH }}
      />
      <div className="relative shrink-0" style={{ width: totalWidth }}>
        {/* Half-hour minor ticks */}
        {halfHourTicks.map((t) => (
          <div
            key={`half-${t}`}
            className="absolute top-0 border-l border-zinc-100"
            style={{ left: (t - range.start) * pxPerMinute, height: HEADER_HEIGHT }}
          />
        ))}
        {/* Hour major ticks with labels */}
        {hourTicks.map((t) => (
          <div
            key={t.min}
            className="absolute top-0 flex flex-col h-full border-l border-zinc-300"
            style={{ left: (t.min - range.start) * pxPerMinute }}
          >
            {(t.min === range.end ||
              (t.min - range.start) % labelStepMinutes === 0) && (
              <span
                className={`px-1 pt-0.5 text-[11px] leading-tight text-zinc-500 ${
                  t.min === range.start
                    ? ""
                    : t.min === range.end
                      ? "-translate-x-full"
                      : "-translate-x-1/2"
                }`}
              >
                {t.label}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
