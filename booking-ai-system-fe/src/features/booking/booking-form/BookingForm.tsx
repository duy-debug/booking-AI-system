"use client";

import { useEffect, useState } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/shared/components/ui/button";
import { ApiError } from "@/shared/types/api-error";
import type { UUID } from "@/shared/types/common";
import { useCourses } from "@/features/course/use-course-queries";
import { useTherapists } from "@/features/therapist/use-therapist-queries";
import { useShops } from "@/features/shop/use-shop-queries";
import { useCheckEligibility } from "@/features/customer/use-customer-queries";
import { useCreateBooking, useUpdateBooking } from "./booking-form.mutations";
import { type EligibilityResult } from "./booking-form.queries";
import { BookingLiveChecks } from "./BookingLiveChecks";
import {
  bookingFormSchema,
  toCreatePayload,
  toUpdatePayload,
  type BookingFormInitial,
  type BookingFormValues,
} from "./booking-form.schema";
import { BUSINESS_HOURS } from "@/shared/config/shop";
import {
  BookingTimeSection,
  CustomerSection,
  CourseSection,
  OptionSection,
  TherapistSection,
  BodyConditionSection,
  BookingSourceSection,
  PreferenceSection,
  NotesSection,
  BookingSummary,
} from "./booking-form-sections";

const TIME_OPTIONS: { value: string; label: string }[] = (() => {
  const out: { value: string; label: string }[] = [];
  const [oh, om] = BUSINESS_HOURS.open.split(":").map(Number);
  const [ch, cm] = BUSINESS_HOURS.close.split(":").map(Number);
  const start = oh * 60 + om;
  const end = ch * 60 + cm;
  for (let m = start; m <= end; m += 15) {
    const hh = String(Math.floor(m / 60)).padStart(2, "0");
    const mm = String(m % 60).padStart(2, "0");
    out.push({ value: `${hh}:${mm}`, label: `${hh}:${mm}` });
  }
  return out;
})();

export interface AvailabilityState {
  available: boolean;
  message?: string;
}

export function BookingForm({
  initial,
  onSaved,
  onCancelBooking,
  onDirtyChange,
}: {
  initial: BookingFormInitial;
  onSaved: (bookingId: UUID) => void;
  onCancelBooking: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const isEdit = initial.mode === "edit";

  const form = useForm<BookingFormValues>({
    resolver: zodResolver(bookingFormSchema),
    defaultValues: {
      shopId: initial.shopId,
      bookingDate: initial.bookingDate,
      startTime: initial.startTime,
      numberOfPeople: 1,
      customerPhone: initial.customerPhone ?? "",
      customerName: initial.customerName ?? "",
      mainCourseId: "",
      addonCourseIds: [],
      therapistRequestType: initial.therapistId ? "specific" : "none",
      requestedTherapistId: initial.therapistId ?? "",
      requestedGender: undefined,
    },
  });

  const { data: shops = [] } = useShops(true);
  const { data: courses = [] } = useCourses(initial.shopId, {
    isActive: true,
  });
  const { data: therapists = [] } = useTherapists(initial.shopId, true);

  const createMut = useCreateBooking();
  const updateMut = useUpdateBooking(isEdit ? (initial.bookingId as UUID) : ("" as UUID));
  const eligibilityMut = useCheckEligibility();

  const [eligibility, setEligibility] = useState<EligibilityResult | null>(null);
  const [availability, setAvailability] = useState<AvailabilityState | null>(
    null,
  );
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Báo drawer trạng thái thay đổi chưa lưu (phục vụ unsaved-change warning)
  const isDirty = form.formState.isDirty;
  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const shopOptions = shops.map((s) => ({ value: s.id, label: s.name }));

  const applyApiErrors = (err: unknown) => {
    if (err instanceof ApiError) {
      const fields = err.fieldErrors();
      for (const [field, message] of Object.entries(fields)) {
        form.setError(field as keyof BookingFormValues, { message });
      }
      if (err.code === "SLOT_CONFLICT" || err.code === "THERAPIST_NOT_AVAILABLE") {
        setAvailability({ available: false, message: err.detail });
        setFormError(err.detail);
      } else if (err.code === "CUSTOMER_IN_NG_LIST") {
        setFormError("SĐT bị cấm đặt lịch (NG list).");
      } else {
        setFormError(err.detail || err.body.title || "Lỗi khi lưu booking.");
      }
    } else {
      setFormError("Lỗi không xác định khi lưu booking.");
    }
  };

  const onSubmit = form.handleSubmit(async (vals) => {
    // Chặn double submit (yêu cầu: không gửi request trùng khi double click).
    // `submitting` state + nút disabled đủ ngăn; không dùng ref (tránh lint refs).
    if (submitting) return;
    setSubmitting(true);
    setFormError(null);
    try {
      if (isEdit && initial.bookingId) {
        await updateMut.mutateAsync(toUpdatePayload(vals));
        onSaved(initial.bookingId);
      } else {
        const created = await createMut.mutateAsync(toCreatePayload(vals));
        onSaved(created.booking_id);
      }
    } catch (err) {
      applyApiErrors(err);
    } finally {
      setSubmitting(false);
    }
  });

  const disabled = submitting;

  return (
    <FormProvider {...form}>
      <form onSubmit={onSubmit} className="space-y-4">
        <BookingLiveChecks
          form={form}
          shopId={initial.shopId}
          submitting={submitting}
          onEligibility={setEligibility}
          onAvailability={setAvailability}
          onAvailabilityLoading={setAvailabilityLoading}
        />
        {formError && (
          <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
            {formError}
          </div>
        )}

        <BookingTimeSection shops={shopOptions} timeOptions={TIME_OPTIONS} />
        <CustomerSection
          eligibility={eligibility}
          eligibilityLoading={eligibilityMut.isPending}
          onCheck={() => {
            const ph = form.getValues("customerPhone");
            if (ph)
              eligibilityMut
                .mutateAsync({ phone: ph, shop_id: initial.shopId })
                .then(setEligibility)
                .catch(() => setEligibility(null));
          }}
        />
        <CourseSection courses={courses} />
        <OptionSection />
        <TherapistSection therapists={therapists} />
        <BodyConditionSection />
        <BookingSourceSection />
        <PreferenceSection />
        <NotesSection />
        <BookingSummary
          courses={courses}
          availability={availability}
          availabilityLoading={availabilityLoading}
        />

        <div className="sticky bottom-0 flex gap-2 border-t border-zinc-200 bg-white py-3">
          {!isEdit && (
            <Button type="submit" disabled={disabled}>
              Tạo booking
            </Button>
          )}
          {isEdit && (
            <Button type="submit" disabled={disabled}>
              Cập nhật giờ
            </Button>
          )}
          {isEdit && (
            <Button
              type="button"
              variant="danger"
              disabled={disabled}
              onClick={onCancelBooking}
            >
              Huỷ booking
            </Button>
          )}
          <Button type="button" variant="ghost" disabled={disabled} onClick={() => form.reset()}>
            Đặt lại
          </Button>
        </div>
      </form>
    </FormProvider>
  );
}
