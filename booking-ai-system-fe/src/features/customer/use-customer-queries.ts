"use client";

import { useApiListQuery, useApiMutation, apiClient } from "@/shared/hooks/api";
import type { UUID } from "@/shared/types/common";
import {
  eligibilityApi,
  restrictionApi,
  toRestrictionUiModel,
  type EligibilityResponse,
  type RestrictionCreateInput,
  type RestrictionResponse,
  type RestrictionUiModel,
  type RestrictionUpdateInput,
} from "./customer.types";

export function useRestrictions(opts?: { phone?: string; isActive?: boolean }) {
  return useApiListQuery<RestrictionResponse, RestrictionUiModel>(
    ["restrictions", opts?.phone, opts?.isActive],
    restrictionApi.list,
    { phone: opts?.phone, is_active: opts?.isActive },
    toRestrictionUiModel,
  );
}

export function useCreateRestriction() {
  return useApiMutation<RestrictionCreateInput, RestrictionResponse>((input) =>
    apiClient.post<RestrictionResponse>(restrictionApi.create, input),
  );
}

export function useUpdateRestriction(id: UUID) {
  return useApiMutation<RestrictionUpdateInput, RestrictionResponse>((input) =>
    apiClient.patch<RestrictionResponse>(restrictionApi.update(id), input),
  );
}

// Kiểm tra SĐT có được đặt không (public, không cần auth)
export function useCheckEligibility() {
  return useApiMutation<{ phone: string; shop_id: UUID }, EligibilityResponse>((input) =>
    apiClient.post<EligibilityResponse>(eligibilityApi.check, input, { anonymous: true }),
  );
}

export type { RestrictionUiModel };
