"use client";

import { useApiMutation, apiClient } from "@/shared/hooks/api";
import type { UUID } from "@/shared/types/common";

// Các API kiểm tra availability / eligibility lấy từ backend (source of truth).
// Căn cứ: docs/frontend-analysis.md §3.6, §3.9.

export interface EligibilityResult {
  eligible: boolean;
  customer: {
    customer_type: "existing";
    customer_id: string;
    name: string | null;
    is_member: boolean;
    member_rank: string | null;
    visit_count: number;
  } | null;
  restriction: null;
}

// Tạo mutation kiểm tra số điện thoại có đủ điều kiện đặt lịch tại shop hay thuộc NG list.
export function useCheckEligibility() {
  return useApiMutation<{ phone: string; shop_id: UUID }, EligibilityResult>(
    (input) =>
      apiClient.post<EligibilityResult>(
        "/api/booking-eligibility-checks",
        input,
        { anonymous: true },
      ),
  );
}

export interface AvailableSlot {
  start_time: string;
  end_time: string;
  duration_minutes: number;
  available: boolean;
  reason_code?:
    | "OUTSIDE_BUSINESS_HOURS"
    | "OUTSIDE_SHIFT"
    | "INSUFFICIENT_AVAILABLE_THERAPISTS"
    | "SLOT_CONFLICT"
    | "START_IN_PAST"
    | "START_TOO_SOON";
  message?: string;
  available_therapist_count?: number;
  required_therapist_count?: number;
}

export interface AvailableTherapist {
  therapist_id: UUID;
  shop_id: UUID;
  name: string;
  gender: "male" | "female";
  available: boolean;
}

// Kiểm tra slot trống cho (shop, date, people, courses, therapist request).
export async function checkAvailableSlots(params: {
  shopId: UUID;
  bookingDate: string;
  numberOfPeople: number;
  mainCourseId: UUID;
  addonCourseIds?: UUID[];
  therapistRequestType?: "none" | "specific" | "gender";
  therapistId?: UUID;
  therapistGender?: "male" | "female";
}): Promise<AvailableSlot[]> {
  const query: Record<string, string> = {
    booking_date: params.bookingDate,
    number_of_people: String(params.numberOfPeople),
    main_course_id: params.mainCourseId,
  };
  if (params.addonCourseIds?.length) {
    query.addon_course_ids = params.addonCourseIds.join(",");
  }
  const effectiveRequestType =
    params.numberOfPeople > 1 && params.therapistRequestType === "specific"
      ? "none"
      : params.therapistRequestType;
  if (effectiveRequestType) {
    query.therapist_request_type = effectiveRequestType;
  }
  if (effectiveRequestType === "specific" && params.therapistId) {
    query.therapist_id = params.therapistId;
  }
  if (effectiveRequestType === "gender" && params.therapistGender) {
    query.therapist_gender = params.therapistGender;
  }

  return apiClient.get<AvailableSlot[]>(
    `/api/shops/${params.shopId}/available-slots`,
    { query, anonymous: true },
  );
}

// Kiểm tra therapist khả dụng trong khung giờ (source of truth cho conflict).
export async function checkAvailableTherapists(params: {
  shopId: UUID;
  bookingDate: string;
  startTime: string;
  endTime: string;
  gender?: "male" | "female" | "any";
}): Promise<AvailableTherapist[]> {
  const query: Record<string, string> = {
    booking_date: params.bookingDate,
    start_time: params.startTime,
    end_time: params.endTime,
  };
  if (params.gender) query.gender = params.gender;

  return apiClient.get<AvailableTherapist[]>(
    `/api/shops/${params.shopId}/available-therapists`,
    { query, anonymous: true },
  );
}
