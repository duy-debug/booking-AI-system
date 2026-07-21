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
  if (params.therapistRequestType) {
    query.therapist_request_type = params.therapistRequestType;
  }
  if (params.therapistId) query.therapist_id = params.therapistId;
  if (params.therapistGender) query.therapist_gender = params.therapistGender;

  const res = await apiClient.get<{ data: AvailableSlot[] }>(
    `/api/shops/${params.shopId}/available-slots`,
    { query, anonymous: true },
  );
  return res.data;
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

  const res = await apiClient.get<{ data: AvailableTherapist[] }>(
    `/api/shops/${params.shopId}/available-therapists`,
    { query, anonymous: true },
  );
  return res.data;
}
