import { z } from "zod";
import type { UUID } from "@/shared/types/common";

// --- Restriction ---
export const restrictionCreateSchema = z.object({
  phone: z.string().min(1, "Số điện thoại bắt buộc"),
  reason: z.string().optional(),
  is_active: z.boolean().default(true),
});
export type RestrictionCreateInput = z.infer<typeof restrictionCreateSchema>;

export const restrictionUpdateSchema = z.object({
  reason: z.string().optional(),
  is_active: z.boolean().optional(),
});
export type RestrictionUpdateInput = z.infer<typeof restrictionUpdateSchema>;

export interface RestrictionResponse {
  restriction_id: UUID;
  phone: string;
  reason: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RestrictionUiModel {
  id: UUID;
  phone: string;
  reason: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export function toRestrictionUiModel(dto: RestrictionResponse): RestrictionUiModel {
  return {
    id: dto.restriction_id,
    phone: dto.phone,
    reason: dto.reason,
    isActive: dto.is_active,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

// --- Eligibility (public) ---
export interface EligibilityCustomer {
  customer_type: "existing";
  customer_id: string;
  name: string | null;
  is_member: boolean;
  member_rank: string | null;
  visit_count: number;
}

export interface EligibilityResponse {
  check_id: UUID;
  phone: string;
  eligible: boolean;
  customer: EligibilityCustomer | null;
  restriction: null;
}

export const restrictionApi = {
  list: "/api/admin/customer-restrictions",
  byId: (id: UUID) => `/api/admin/customer-restrictions/${id}`,
  create: "/api/admin/customer-restrictions",
  update: (id: UUID) => `/api/admin/customer-restrictions/${id}`,
};

export const eligibilityApi = {
  check: "/api/booking-eligibility-checks",
};
