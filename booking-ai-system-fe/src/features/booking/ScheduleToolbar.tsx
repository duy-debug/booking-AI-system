"use client";

import { Select } from "@/shared/components/ui/select";
import { Button } from "@/shared/components/ui/button";
import { TIME_STEPS, type TimeStep } from "./schedule.theme";
import type { ISODate, UUID } from "@/shared/types/common";
import { todayShopDate } from "@/shared/lib/datetime";

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
}

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
}: ScheduleToolbarProps) {
  return (
    <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-zinc-200 bg-white p-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-zinc-600">Ngày</label>
        <div className="flex items-center gap-1">
          <Button variant="secondary" onClick={onPrevDay} className="px-2 py-2">
            ‹
          </Button>
          <input
            type="date"
            value={date}
            onChange={(e) => onDateChange(e.target.value)}
            className="rounded-lg border border-zinc-300 px-3 py-2 text-sm"
          />
          <Button variant="secondary" onClick={onNextDay} className="px-2 py-2">
            ›
          </Button>
        </div>
      </div>

      <Select
        label="Shop"
        name="shop"
        value={shopId ?? ""}
        onChange={(e) => onShopChange(e.target.value)}
        options={[
          { value: "", label: "Chọn shop..." },
          ...shops.map((s) => ({ value: s.id, label: s.name })),
        ]}
      />

      <Select
        label="Độ chia"
        name="step"
        value={String(step)}
        onChange={(e) => onStepChange(Number(e.target.value) as TimeStep)}
        options={TIME_STEPS.map((s) => ({ value: String(s), label: `${s} phút` }))}
      />

      <Button variant="ghost" onClick={() => onDateChange(todayShopDate())}>
        Hôm nay
      </Button>
    </div>
  );
}
