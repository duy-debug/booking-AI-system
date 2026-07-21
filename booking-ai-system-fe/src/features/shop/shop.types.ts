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
  createdAt: string;
  updatedAt: string;
}

// --- Mapper (DTO -> UI model, nguyên tắc 7) ---
export function toShopUiModel(dto: AdminShopResponse): ShopUiModel {
  return {
    id: dto.shop_id,
    code: dto.shop_code,
    posCode: dto.pos_shop_code,
    name: dto.name,
    address: dto.address,
    phone: dto.phone,
    isActive: dto.is_active,
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
