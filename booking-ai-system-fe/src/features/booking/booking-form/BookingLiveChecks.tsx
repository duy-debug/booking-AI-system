"use client";

import { useEffect, useRef } from "react";
import { useWatch, type UseFormReturn } from "react-hook-form";
import { useCheckEligibility } from "@/features/customer/use-customer-queries";
import {
  checkAvailableSlots,
  type EligibilityResult,
} from "./booking-form.queries";
import type { UUID } from "@/shared/types/common";
import type { AvailabilityState } from "./BookingForm";
import type { BookingFormValues } from "./booking-form.schema";

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

// Component con tách biệt các effect kiểm tra live (eligibility + availability)
// khỏi form root. Dùng useWatch riêng -> chỉ component này re-render khi field
// thay đổi, không kéo toàn bộ 10 section form re-render (nguyên tắc hiệu năng).
export function BookingLiveChecks({
  form,
  shopId,
  submitting,
  onEligibility,
  onAvailability,
  onAvailabilityLoading,
}: {
  form: UseFormReturn<BookingFormValues>;
  shopId: UUID;
  submitting: boolean;
  onEligibility: (r: EligibilityResult | null) => void;
  onAvailability: (a: AvailabilityState | null) => void;
  onAvailabilityLoading: (loading: boolean) => void;
}) {
  const phone = useWatch({ control: form.control, name: "customerPhone" });
  const mainCourseId = useWatch({ control: form.control, name: "mainCourseId" });
  const bookingDate = useWatch({ control: form.control, name: "bookingDate" });
  const startTime = useWatch({ control: form.control, name: "startTime" });
  const numberOfPeople = useWatch({ control: form.control, name: "numberOfPeople" });
  const addonCourseIds = useWatch({ control: form.control, name: "addonCourseIds" });
  const therapistRequestType = useWatch({ control: form.control, name: "therapistRequestType" });
  const requestedTherapistId = useWatch({ control: form.control, name: "requestedTherapistId" });
  const requestedGender = useWatch({ control: form.control, name: "requestedGender" });

  const eligibilityMut = useCheckEligibility();
  const availabilityReqId = useRef(0);

  // Debounce 400ms eligibility check khi SĐT thay đổi
  useEffect(() => {
    if (!phone || !/^\+?\d{6,15}$/.test(phone)) {
      onEligibility(null);
      return;
    }
    const t = setTimeout(() => {
      eligibilityMut
        .mutateAsync({ phone, shop_id: shopId })
        .then(onEligibility)
        .catch(() => onEligibility(null));
    }, 400);
    return () => clearTimeout(t);
  }, [phone, shopId, eligibilityMut, onEligibility]);

  // Debounce 400ms availability check (backend source of truth), abort stale.
  useEffect(() => {
    if (
      !mainCourseId ||
      !bookingDate ||
      !startTime ||
      !TIME_RE.test(startTime) ||
      numberOfPeople < 1 ||
      numberOfPeople > 3
    ) {
      onAvailability(null);
      return;
    }
    if (submitting) return;
    const reqId = ++availabilityReqId.current;
    const t = setTimeout(async () => {
      onAvailabilityLoading(true);
      try {
        const slots = await checkAvailableSlots({
          shopId,
          bookingDate,
          numberOfPeople,
          mainCourseId: mainCourseId as UUID,
          addonCourseIds: (addonCourseIds as UUID[]) ?? [],
          therapistRequestType,
          therapistId: requestedTherapistId ? (requestedTherapistId as UUID) : undefined,
          therapistGender: requestedGender,
        });
        if (reqId !== availabilityReqId.current) return;
        const match = slots.find((s) => s.start_time.startsWith(startTime));
        if (!match) {
          onAvailability({ available: false, message: "Ngoài khung giờ" });
        } else if (!match.available) {
          onAvailability({ available: false, message: "Đã có booking khác" });
        } else {
          onAvailability({ available: true });
        }
      } catch {
        if (reqId !== availabilityReqId.current) return;
        onAvailability({ available: false, message: "Lỗi kiểm tra lịch" });
      } finally {
        if (reqId === availabilityReqId.current) onAvailabilityLoading(false);
      }
    }, 400);
    return () => clearTimeout(t);
  }, [
    mainCourseId,
    bookingDate,
    startTime,
    numberOfPeople,
    addonCourseIds,
    therapistRequestType,
    requestedTherapistId,
    requestedGender,
    shopId,
    submitting,
    onAvailability,
    onAvailabilityLoading,
  ]);

  return null;
}
