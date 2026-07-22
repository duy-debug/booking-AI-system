"use client";

import { Button } from "@/shared/components/ui/button";
import { TIME_STEPS, type TimeStep } from "./schedule.theme";
import { STATUS_STYLES } from "./schedule.theme";
import type { ISODate, UUID } from "@/shared/types/common";
import { todayShopDate } from "@/shared/lib/datetime";
import type { ScheduleViewModel } from "./schedule.types";

interface ScheduleToolbarProps {
  date: ISODate;
  onDateChange: (d: ISODate) => void;
  shopId: UUID | null;
  onShopChange: (id: UUID) => void;
  shops: { id: UUID; name: string }[];
  step: TimeStep;
  onStepChange: (s: TimeStep) => void;
  onPrevDay: () => void;
  onNextDay: () => void;
  scheduleData: ScheduleViewModel | null;
  shopsLoading?: boolean;
}

const LEGEND_ITEMS = [
  { key: "confirmed", label: "Confirmed", dot: STATUS_STYLES.confirmed.dot },
  { key: "pending", label: "Pending", dot: STATUS_STYLES.pending.dot },
  { key: "checked-in", label: "Check-in", dot: STATUS_STYLES["checked-in"].dot },
  { key: "completed", label: "Done", dot: STATUS_STYLES.completed.dot },
  { key: "cancelled", label: "Huỷ", dot: STATUS_STYLES.cancelled.dot },
] as const;

// Cung cấp bộ điều khiển shop, ngày, step và điều hướng ngày cho timeline booking.
export function ScheduleToolbar({
  date,
  onDateChange,
  shopId,
  onShopChange,
  shops,
  step,
  onStepChange,
  onPrevDay,
  onNextDay,
  scheduleData,
  shopsLoading,
}: ScheduleToolbarProps) {
  const therapistCount = scheduleData?.resources.length ?? 0;
  const bookingCount = scheduleData?.bookings.length ?? 0;

  // Count by status for display
  const statusCounts = scheduleData?.bookings.reduce<Record<string, number>>((acc, b) => {
    acc[b.status] = (acc[b.status] || 0) + 1;
    return acc;
  }, {}) ?? {};

  return (
    <div className="sticky top-0 z-40 bg-zinc-50 border-b border-zinc-200 px-2 py-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        {/* Date navigation */}
        <div className="flex items-center gap-0.5">
          <Button variant="ghost" onClick={onPrevDay} className="px-1.5 py-1 h-7 text-sm" aria-label="Ngày trước">
            ‹
          </Button>
          <input
            type="date"
            value={date}
            onChange={(e) => onDateChange(e.target.value)}
            className="rounded border border-zinc-300 px-1.5 py-1 text-xs h-7 w-32"
          />
          <Button variant="ghost" onClick={onNextDay} className="px-1.5 py-1 h-7 text-sm" aria-label="Ngày sau">
            ›
          </Button>
          <Button variant="ghost" onClick={() => onDateChange(todayShopDate())} className="px-2 py-1 h-7 text-xs">
            Hôm nay
          </Button>
        </div>

        <div className="w-px h-5 bg-zinc-300" />

        {/* Shop selector */}
        <div className="flex items-center gap-1">
          <label className="text-xs text-zinc-500">Shop:</label>
          <select
            value={shopId ?? ""}
            onChange={(e) => onShopChange(e.target.value)}
            className="rounded border border-zinc-300 px-1.5 py-1 text-xs h-7 max-w-[140px]"
            disabled={shopsLoading}
          >
            {shopsLoading ? (
              <option value="">Đang tải...</option>
            ) : (
              <>
                <option value="">Chọn shop</option>
                {shops.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </>
            )}
          </select>
        </div>

        <div className="w-px h-5 bg-zinc-300" />

        {/* Step selector */}
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">Bước:</span>
          <div className="flex rounded border border-zinc-300 overflow-hidden">
            {TIME_STEPS.map((s) => (
              <button
                key={s}
                onClick={() => onStepChange(s)}
                className={`px-1.5 py-1 text-xs transition-colors ${
                  step === s
                    ? "bg-blue-600 text-white"
                    : "bg-white text-zinc-600 hover:bg-zinc-100"
                }`}
                aria-label={`Chia ${s} phút`}
              >
                {s}&apos;
              </button>
            ))}
          </div>
        </div>

        <div className="w-px h-5 bg-zinc-300" />

        {/* Stats */}
        <div className="flex items-center gap-2 text-xs text-zinc-600">
          <span>Therapist: <b>{therapistCount}</b></span>
          <span>Booking: <b>{bookingCount}</b></span>
        </div>

        <div className="w-px h-5 bg-zinc-300" />

        {/* Status legend */}
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          {LEGEND_ITEMS.map((item) => (
            <span key={item.key} className="flex items-center gap-1">
              <span className={`inline-block w-2 h-2 rounded-full ${item.dot}`} />
              {item.label}
              {(statusCounts[item.key] ?? 0) > 0 && (
                <span className="text-zinc-400">({statusCounts[item.key]})</span>
              )}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
