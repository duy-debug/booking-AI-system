"use client";

import type { TimeRange } from "./schedule.utils";

interface TimeGridProps {
  range: TimeRange;
  height: number;
  pxPerMinute: number;
  step: number;
}

// Vẽ các đường chia phút, giờ và step làm nền căn chỉnh cho mọi layer trên timeline.
export function TimeGrid({ range, height, pxPerMinute, step }: TimeGridProps) {
  const span = range.end - range.start;

  // Step minor lines (drive by step)
  const minorTicks: number[] = [];
  for (let t = step; t < span; t += step) {
    if (t % 60 !== 0) minorTicks.push(range.start + t);
  }

  // Half-hour lines (every 60 min, offset 30) - only if step doesn't already cover it
  const hasHalfHourTick = 30 % step === 0;
  const halfTicks: number[] = [];
  if (!hasHalfHourTick) {
    for (let t = 30; t < span; t += 60) halfTicks.push(range.start + t);
  }

  // Hour major lines
  const hourTicks: number[] = [];
  for (let t = 0; t <= span; t += 60) hourTicks.push(range.start + t);

  return (
    <div className="pointer-events-none absolute inset-0">
      {/* Step minor lines */}
      {minorTicks.map((t) => (
        <div
          key={`step-${t}`}
          className="absolute top-0 border-l border-zinc-50"
          style={{ left: (t - range.start) * pxPerMinute, height }}
        />
      ))}
      {/* Half-hour lines (only if not already covered by step) */}
      {halfTicks.map((t) => (
        <div
          key={`30-${t}`}
          className="absolute top-0 border-l border-zinc-100"
          style={{ left: (t - range.start) * pxPerMinute, height }}
        />
      ))}
      {/* Hour major */}
      {hourTicks.map((t) => (
        <div
          key={`60-${t}`}
          className="absolute top-0 border-l border-zinc-200"
          style={{ left: (t - range.start) * pxPerMinute, height }}
        />
      ))}
    </div>
  );
}
