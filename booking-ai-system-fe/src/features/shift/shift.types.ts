import { z } from "zod";
import type { ISODate, ISOTime, UUID } from "@/shared/types/common";

export const shiftCreateSchema = z.object({
  shop_id: z.string().min(1),
  therapist_id: z.string().min(1),
  work_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Ngày YYYY-MM-DD"),
  start_time: z.string().regex(/^\d{2}:\d{2}$/, "Giờ HH:MM"),
  end_time: z.string().regex(/^\d{2}:\d{2}$/, "Giờ HH:MM"),
  is_active: z.boolean().default(true),
});
export type ShiftCreateInput = z.infer<typeof shiftCreateSchema>;

export const shiftUpdateSchema = z.object({
  start_time: z.string().regex(/^\d{2}:\d{2}$/).optional(),
  end_time: z.string().regex(/^\d{2}:\d{2}$/).optional(),
  is_active: z.boolean().optional(),
});
export type ShiftUpdateInput = z.infer<typeof shiftUpdateSchema>;

export interface ShiftResponse {
  shift_id: UUID;
  shop_id: UUID;
  therapist_id: UUID;
  work_date: ISODate;
  start_time: ISOTime;
  end_time: ISOTime;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ShiftUiModel {
  id: UUID;
  shopId: UUID;
  therapistId: UUID;
  workDate: ISODate;
  startTime: ISOTime;
  endTime: ISOTime;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

// Chuyển shift DTO sang UI model camelCase và giữ nguyên các mốc ngày giờ phục vụ form.
export function toShiftUiModel(dto: ShiftResponse): ShiftUiModel {
  return {
    id: dto.shift_id,
    shopId: dto.shop_id,
    therapistId: dto.therapist_id,
    workDate: dto.work_date,
    startTime: dto.start_time,
    endTime: dto.end_time,
    isActive: dto.is_active,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

export const shiftApi = {
  listByShop: (shopId: UUID) => `/api/admin/shops/${shopId}/therapist-shifts`,
  byId: (id: UUID) => `/api/admin/therapist-shifts/${id}`,
  create: "/api/admin/therapist-shifts",
  update: (id: UUID) => `/api/admin/therapist-shifts/${id}`,
};
