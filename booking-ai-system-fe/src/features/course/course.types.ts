import { z } from "zod";
import type { CourseType, DecimalString, UUID } from "@/shared/types/common";

export const courseCreateSchema = z.object({
  pos_course_code: z.string().min(1, "Mã course bắt buộc"),
  name: z.string().min(1, "Tên course bắt buộc"),
  duration_minutes: z.coerce
    .number()
    .int()
    .min(15, "Tối thiểu 15 phút")
    .refine((n) => n % 15 === 0, "Phải là bội của 15"),
  price: z.coerce.number().min(0, "Giá không âm"),
  course_type: z.enum(["main", "addon"]),
  is_active: z.boolean().default(true),
});
export type CourseCreateInput = z.infer<typeof courseCreateSchema>;

export const courseUpdateSchema = courseCreateSchema.partial();
export type CourseUpdateInput = z.infer<typeof courseUpdateSchema>;

export interface AdminCourseResponse {
  course_id: UUID;
  shop_id: UUID;
  pos_course_code: string;
  name: string;
  duration_minutes: number;
  price: DecimalString; // backend trả string
  course_type: CourseType;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CourseUiModel {
  id: UUID;
  shopId: UUID;
  posCode: string;
  name: string;
  durationMinutes: number;
  price: number; // normalized thành number
  courseType: CourseType;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export function toCourseUiModel(dto: AdminCourseResponse): CourseUiModel {
  return {
    id: dto.course_id,
    shopId: dto.shop_id,
    posCode: dto.pos_course_code,
    name: dto.name,
    durationMinutes: dto.duration_minutes,
    price: Number(dto.price), // Decimal -> number
    courseType: dto.course_type,
    isActive: dto.is_active,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

export const courseApi = {
  listByShop: (shopId: UUID) => `/api/admin/shops/${shopId}/courses`,
  byId: (id: UUID) => `/api/admin/courses/${id}`,
  create: (shopId: UUID) => `/api/admin/shops/${shopId}/courses`,
  update: (id: UUID) => `/api/admin/courses/${id}`,
};
