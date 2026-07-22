import { z } from "zod";
import type { Gender, UUID } from "@/shared/types/common";

export const therapistCreateSchema = z.object({
  pos_therapist_code: z.string().min(1, "Mã therapist bắt buộc"),
  name: z.string().min(1, "Tên bắt buộc"),
  gender: z.enum(["male", "female"]),
  is_active: z.boolean().default(true),
});
export type TherapistCreateInput = z.infer<typeof therapistCreateSchema>;

export const therapistUpdateSchema = therapistCreateSchema.partial();
export type TherapistUpdateInput = z.infer<typeof therapistUpdateSchema>;

export interface TherapistResponse {
  therapist_id: UUID;
  shop_id: UUID;
  pos_therapist_code: string;
  name: string;
  gender: Gender;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TherapistUiModel {
  id: UUID;
  shopId: UUID;
  posCode: string;
  name: string;
  gender: Gender;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

// Ánh xạ therapist DTO sang UI model camelCase và giữ nguyên ID dùng cho phân công booking.
export function toTherapistUiModel(dto: TherapistResponse): TherapistUiModel {
  return {
    id: dto.therapist_id,
    shopId: dto.shop_id,
    posCode: dto.pos_therapist_code,
    name: dto.name,
    gender: dto.gender,
    isActive: dto.is_active,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

export const therapistApi = {
  listByShop: (shopId: UUID) => `/api/admin/shops/${shopId}/therapists`,
  byId: (id: UUID) => `/api/admin/therapists/${id}`,
  create: (shopId: UUID) => `/api/admin/shops/${shopId}/therapists`,
  update: (id: UUID) => `/api/admin/therapists/${id}`,
};
