"use client";

import { useApiListQuery, useApiMutation, apiClient } from "@/shared/hooks/api";
import type { UUID } from "@/shared/types/common";
import {
  therapistApi,
  toTherapistUiModel,
  type TherapistCreateInput,
  type TherapistResponse,
  type TherapistUiModel,
  type TherapistUpdateInput,
} from "./therapist.types";

export function useTherapists(shopId: UUID, isActive?: boolean) {
  return useApiListQuery<TherapistResponse, TherapistUiModel>(
    ["therapists", shopId, isActive],
    therapistApi.listByShop(shopId),
    isActive === undefined ? undefined : { is_active: isActive },
    toTherapistUiModel,
  );
}

export function useCreateTherapist(shopId: UUID) {
  return useApiMutation<TherapistCreateInput, TherapistResponse>((input) =>
    apiClient.post<TherapistResponse>(therapistApi.create(shopId), input),
  );
}

export function useUpdateTherapist(id: UUID) {
  return useApiMutation<TherapistUpdateInput, TherapistResponse>((input) =>
    apiClient.patch<TherapistResponse>(therapistApi.update(id), input),
  );
}

export type { TherapistUiModel };
