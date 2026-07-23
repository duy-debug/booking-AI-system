import { z } from "zod";
import type { UUID } from "@/shared/types/common";

// --- Zod schemas (validation, nguyên tắc 10) ---
export const shopCreateSchema = z.object({
  shop_code: z.string().min(1, "Mã shop bắt buộc"),
  pos_shop_code: z.string().min(1, "Mã POS bắt buộc"),
  name: z.string().min(1, "Tên shop bắt buộc"),
  address: z.string().optional(),
  phone: z.string().optional(),
  is_active: z.boolean().default(true),
  therapist_break_minutes: z.union([
    z.literal(0),
    z.literal(5),
    z.literal(10),
    z.literal(15),
  ]).default(0),
});
export type ShopCreateInput = z.infer<typeof shopCreateSchema>;

export const shopUpdateSchema = shopCreateSchema.partial();
export type ShopUpdateInput = z.infer<typeof shopUpdateSchema>;

// --- Backend DTO (raw) ---
export interface AdminShopResponse {
  shop_id: UUID;
  shop_code: string;
  pos_shop_code: string;
  name: string;
  address: string | null;
  phone: string | null;
  is_active: boolean;
  therapist_break_minutes: 0 | 5 | 10 | 15;
  created_at: string;
  updated_at: string;
}

export interface PublicShopResponse {
  shop_id: UUID;
  shop_code: string;
  name: string;
  address: string | null;
  phone: string | null;
}

// --- UI model ---
export interface ShopUiModel {
  id: UUID;
  code: string;
  posCode: string;
  name: string;
  address: string | null;
  phone: string | null;
  isActive: boolean;
  therapistBreakMinutes: 0 | 5 | 10 | 15;
  createdAt: string;
  updatedAt: string;
}

// --- Mapper (DTO -> UI model, nguyên tắc 7) ---
// Ánh xạ DTO snake_case của shop từ backend sang model camelCase an toàn cho UI.
export function toShopUiModel(dto: AdminShopResponse): ShopUiModel {
  return {
    id: dto.shop_id,
    code: dto.shop_code,
    posCode: dto.pos_shop_code,
    name: dto.name,
    address: dto.address,
    phone: dto.phone,
    isActive: dto.is_active,
    therapistBreakMinutes: dto.therapist_break_minutes,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

// --- API paths ---
export const shopApi = {
  list: "/api/admin/shops",
  byId: (id: UUID) => `/api/admin/shops/${id}`,
  create: "/api/admin/shops",
  update: (id: UUID) => `/api/admin/shops/${id}`,
};
