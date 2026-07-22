"use client";

import { useApiListQuery, useApiMutation, apiClient } from "@/shared/hooks/api";
import type { UUID } from "@/shared/types/common";
import {
  courseApi,
  toCourseUiModel,
  type AdminCourseResponse,
  type CourseCreateInput,
  type CourseUiModel,
  type CourseUpdateInput,
} from "./course.types";

// Tải course theo shop cùng bộ lọc loại/trạng thái và ánh xạ dữ liệu để component sử dụng trực tiếp.
export function useCourses(shopId: UUID, opts?: { courseType?: string; isActive?: boolean }) {
  return useApiListQuery<AdminCourseResponse, CourseUiModel>(
    ["courses", shopId, opts?.courseType, opts?.isActive],
    courseApi.listByShop(shopId),
    {
      course_type: opts?.courseType,
      is_active: opts?.isActive,
    },
    toCourseUiModel,
  );
}

// Tạo mutation thêm course mới vào shop đang chọn.
export function useCreateCourse(shopId: UUID) {
  return useApiMutation<CourseCreateInput, AdminCourseResponse>((input) =>
    apiClient.post<AdminCourseResponse>(courseApi.create(shopId), input),
  );
}

// Tạo mutation cập nhật course hiện có theo ID.
export function useUpdateCourse(id: UUID) {
  return useApiMutation<CourseUpdateInput, AdminCourseResponse>((input) =>
    apiClient.patch<AdminCourseResponse>(courseApi.update(id), input),
  );
}

export type { CourseUiModel };
