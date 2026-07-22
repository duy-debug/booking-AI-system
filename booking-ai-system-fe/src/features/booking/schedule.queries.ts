"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/shared/hooks/api";
import { toScheduleViewModel } from "./schedule.mapper";
import { FULL_DAY_RANGE } from "./schedule.utils";
import type { ScheduleResponseRaw } from "./schedule.api";
import type { ScheduleViewModel } from "./schedule.types";
import type { ISODate, UUID } from "@/shared/types/common";

// Gọi endpoint tổng hợp timeline theo shop/ngày và chuyển raw response thành ScheduleViewModel.
async function fetchSchedule(
  shopId: UUID,
  date: ISODate,
): Promise<ScheduleViewModel> {
  const raw = await apiClient.get<ScheduleResponseRaw>("/api/admin/booking", {
    query: { shop_id: shopId, date },
  });
  return toScheduleViewModel(raw, FULL_DAY_RANGE);
}

// Quản lý cache timeline và chỉ tải khi đã có shop cùng ngày hợp lệ.
export function useScheduleData(shopId: UUID | null, date: ISODate) {
  return useQuery<ScheduleViewModel, Error>({
    queryKey: ["schedule", shopId, date],
    queryFn: () => fetchSchedule(shopId as UUID, date),
    enabled: !!shopId,
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}
