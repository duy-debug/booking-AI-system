"use client";

import { useState } from "react";
import { addDays, format, parseISO } from "date-fns";
import { useQueryClient } from "@tanstack/react-query";
import { ScheduleToolbar } from "@/features/booking/ScheduleToolbar";
import { ScheduleBoard } from "@/features/booking/ScheduleBoard";
import { useShops } from "@/features/shop/use-shop-queries";
import { useScheduleData } from "@/features/booking/schedule.queries";
import { type Selection } from "@/features/booking/SelectionLayer";
import type { BookingViewModel } from "@/features/booking/schedule.types";
import { type TimeStep } from "@/features/booking/schedule.theme";
import { BookingDrawer, type BookingDrawerState } from "@/features/booking/booking-form/BookingDrawer";
import { todayShopDate } from "@/shared/lib/datetime";
import type { UUID } from "@/shared/types/common";

export default function AdminBookingsPage() {
  const [date, setDate] = useState<string>(todayShopDate());
  const [shopId, setShopId] = useState<UUID | null>(null);
  const [step, setStep] = useState<TimeStep>(15);
  const [drawer, setDrawer] = useState<BookingDrawerState>(null);

  const queryClient = useQueryClient();
  const shopsQuery = useShops(true);
  const shops = (shopsQuery.data ?? []).map((s) => ({ id: s.id, name: s.name }));

  const activeShopId = shopId ?? shops[0]?.id ?? null;

  const scheduleQuery = useScheduleData(activeShopId, date);

  const shiftDay = (delta: number) => {
    const next = addDays(parseISO(date), delta);
    setDate(format(next, "yyyy-MM-dd"));
  };

  const handleCreate = (sel: Selection) => {
    if (!activeShopId) return;
    setDrawer({ kind: "create", selection: sel, shopId: activeShopId, bookingDate: date });
  };

  const handleSelectBooking = (b: BookingViewModel) => {
    if (!activeShopId) return;
    setDrawer({ kind: "edit", booking: b, shopId: activeShopId, bookingDate: date });
  };

  const handleSaved = (bookingId: UUID) => {
    queryClient.invalidateQueries({ queryKey: ["schedule", activeShopId, date] });
    queryClient.invalidateQueries({ queryKey: ["admin-booking", bookingId] });
    setDrawer(null);
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-zinc-900">Quản lý Booking</h1>
      <ScheduleToolbar
        date={date}
        onDateChange={setDate}
        shopId={activeShopId}
        onShopChange={(id) => setShopId(id || null)}
        shops={shops}
        step={step}
        onStepChange={setStep}
        onPrevDay={() => shiftDay(-1)}
        onNextDay={() => shiftDay(1)}
      />
      <ScheduleBoard
        schedule={scheduleQuery.data}
        isLoading={scheduleQuery.isLoading}
        isError={scheduleQuery.isError}
        error={scheduleQuery.error ?? undefined}
        step={step}
        onSelectBooking={handleSelectBooking}
        onCreateBooking={handleCreate}
      />
      <BookingDrawer state={drawer} onClose={() => setDrawer(null)} onSaved={handleSaved} />
    </div>
  );
}
