"use client";

import { useState, useCallback, useMemo } from "react";
import { addDays, format, parseISO } from "date-fns";
import { useQueryClient } from "@tanstack/react-query";
import { ScheduleToolbar } from "@/features/booking/ScheduleToolbar";
import { ScheduleBoard } from "@/features/booking/ScheduleBoard";
import { useShops } from "@/features/shop/use-shop-queries";
import { useScheduleData } from "@/features/booking/schedule.queries";
import { type Selection } from "@/features/booking/SelectionLayer";
import type { BookingViewModel } from "@/features/booking/schedule.types";
import { BookingDrawer, type BookingDrawerState } from "@/features/booking/booking-form/BookingDrawer";
import { todayShopDate } from "@/shared/lib/datetime";
import type { UUID } from "@/shared/types/common";

// Điều phối shop, ngày, timeline, selection và modal để tạo hoặc chỉnh sửa booking trên một màn hình.
export default function AdminBookingsPage() {
  const [date, setDate] = useState<string>(todayShopDate());
  const [shopId, setShopId] = useState<UUID | null>(null);
  const [drawer, setDrawer] = useState<BookingDrawerState>(null);

  const queryClient = useQueryClient();
  const shopsQuery = useShops(true);
  // Rút gọn shop model thành option ID/tên và giữ reference ổn định cho toolbar.
  const shops = useMemo(
    () => (shopsQuery.data ?? []).map((s) => ({ id: s.id, name: s.name })),
    [shopsQuery.data],
  );

  const activeShopId = shopId ?? shops[0]?.id ?? null;
  const activeShop = useMemo(
    () => shopsQuery.data?.find((shop) => shop.id === activeShopId) ?? null,
    [activeShopId, shopsQuery.data],
  );

  const scheduleQuery = useScheduleData(activeShopId, date);

  // Dịch ngày timeline theo số ngày dương hoặc âm và lưu lại theo định dạng API yyyy-MM-dd.
  const shiftDay = useCallback((delta: number) => {
    const next = addDays(parseISO(date), delta);
    setDate(format(next, "yyyy-MM-dd"));
  }, [date]);

  // Mở drawer tạo mới từ selection, giữ đúng shop, ngày, timezone và giới hạn đặt trước.
  const handleCreate = useCallback((sel: Selection) => {
    if (!activeShopId) return;
    setDrawer({
      kind: "create",
      selection: sel,
      shopId: activeShopId,
      bookingDate: date,
      timezone: scheduleQuery.data?.timezone ?? "Asia/Ho_Chi_Minh",
      minimumBookingAdvanceMinutes: scheduleQuery.data?.minimumBookingAdvanceMinutes ?? 15,
    });
  }, [activeShopId, date, scheduleQuery.data]);

  // Mở drawer chỉnh sửa khi người dùng chọn một booking active hoặc nút chi tiết booking hủy.
  const handleSelectBooking = useCallback((b: BookingViewModel) => {
    if (!activeShopId) return;
    setDrawer({ kind: "edit", booking: b, shopId: activeShopId, bookingDate: date });
  }, [activeShopId, date]);

  // Làm mới cache timeline/detail sau khi lưu rồi đóng drawer hiện tại.
  const handleSaved = useCallback((bookingId: UUID) => {
    queryClient.invalidateQueries({ queryKey: ["schedule", activeShopId, date] });
    queryClient.invalidateQueries({ queryKey: ["admin-booking", bookingId] });
    setDrawer(null);
  }, [queryClient, activeShopId, date]);

  return (
    <div className="flex flex-col h-full">
      <ScheduleToolbar
        date={date}
        onDateChange={setDate}
        shopId={activeShopId}
        onShopChange={(id) => setShopId(id || null)}
        shops={shops}
        activeShop={activeShop}
        onPrevDay={() => shiftDay(-1)}
        onNextDay={() => shiftDay(1)}
        scheduleData={scheduleQuery.data ?? null}
        shopsLoading={shopsQuery.isLoading}
      />
      <div className="flex-1 min-h-0 px-2 pb-2">
        <ScheduleBoard
          schedule={scheduleQuery.data}
          isLoading={scheduleQuery.isLoading}
          isError={scheduleQuery.isError}
          error={scheduleQuery.error ?? undefined}
          onSelectBooking={handleSelectBooking}
          onCreateBooking={handleCreate}
        />
      </div>
      <BookingDrawer state={drawer} onClose={() => setDrawer(null)} onSaved={handleSaved} />
    </div>
  );
}
