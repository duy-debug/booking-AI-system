"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/shared/hooks/api";
import { toScheduleViewModel } from "./schedule.mapper";
import { buildTimelineRange } from "./schedule.utils";
import { BUSINESS_HOURS } from "@/shared/config/shop";
import type { ScheduleResponseRaw } from "./schedule.api";
import type { ScheduleViewModel } from "./schedule.types";
import type { ISODate, UUID } from "@/shared/types/common";

// Adapter gọi endpoint tổng hợp GET /api/admin/schedule (1 request, không N+1).
// Căn cứ: app/api/admin/schedule.py. Trả về shop + therapists + shifts +
// blocked_ranges + bookings (kèm reservation.therapist_id + courses) + statuses.
// Đã thay thế adapter cũ gọi N request detail (booking-form + schedule cũ).

async function fetchSchedule(
  shopId: UUID,
  date: ISODate,
): Promise<ScheduleViewModel> {
  const timeline = buildTimelineRange(BUSINESS_HOURS.open, BUSINESS_HOURS.close);
  const raw = await apiClient.get<ScheduleResponseRaw>("/api/admin/booking", {
    query: { shop_id: shopId, date },
  });
  return toScheduleViewModel(raw, timeline);
}

export function useScheduleData(shopId: UUID | null, date: ISODate) {
  return useQuery<ScheduleViewModel, Error>({
    queryKey: ["schedule", shopId, date],
    queryFn: () => fetchSchedule(shopId as UUID, date),
    enabled: !!shopId,
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}
