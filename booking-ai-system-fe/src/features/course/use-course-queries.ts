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

export function useCreateCourse(shopId: UUID) {
  return useApiMutation<CourseCreateInput, AdminCourseResponse>((input) =>
    apiClient.post<AdminCourseResponse>(courseApi.create(shopId), input),
  );
}

export function useUpdateCourse(id: UUID) {
  return useApiMutation<CourseUpdateInput, AdminCourseResponse>((input) =>
    apiClient.patch<AdminCourseResponse>(courseApi.update(id), input),
  );
}

export type { CourseUiModel };
