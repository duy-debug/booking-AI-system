"use client";

import { useApiListQuery, useApiMutation, apiClient } from "@/shared/hooks/api";
import type { UUID } from "@/shared/types/common";
import {
  shiftApi,
  toShiftUiModel,
  type ShiftCreateInput,
  type ShiftResponse,
  type ShiftUiModel,
  type ShiftUpdateInput,
} from "./shift.types";

export function useShifts(
  shopId: UUID,
  opts?: { workDate?: string; therapistId?: UUID; isActive?: boolean },
) {
  return useApiListQuery<ShiftResponse, ShiftUiModel>(
    ["shifts", shopId, opts?.workDate, opts?.therapistId, opts?.isActive],
    shiftApi.listByShop(shopId),
    {
      work_date: opts?.workDate,
      therapist_id: opts?.therapistId,
      is_active: opts?.isActive,
    },
    toShiftUiModel,
  );
}

export function useCreateShift() {
  return useApiMutation<ShiftCreateInput, ShiftResponse>((input) =>
    apiClient.post<ShiftResponse>(shiftApi.create, input),
  );
}

export function useUpdateShift(id: UUID) {
  return useApiMutation<ShiftUpdateInput, ShiftResponse>((input) =>
    apiClient.patch<ShiftResponse>(shiftApi.update(id), input),
  );
}

export type { ShiftUiModel };
