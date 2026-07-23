"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@/shared/types/api-error";
import { useAlert } from "@/shared/components/AlertProvider";
import type { UUID } from "@/shared/types/common";
import { useCourses } from "@/features/course/use-course-queries";
import { useTherapists } from "@/features/therapist/use-therapist-queries";
import type { CourseUiModel } from "@/features/course/course.types";
import type { TherapistUiModel } from "@/features/therapist/therapist.types";
import { useCheckEligibility } from "@/features/customer/use-customer-queries";
import { useCreateBooking, useUpdateBooking } from "./booking-form.mutations";
import { type EligibilityResult } from "./booking-form.queries";
import { BookingLiveChecks } from "./BookingLiveChecks";
import {
  bookingFormSchema,
  bookingUpdateFormSchema,
  toCreatePayload,
  toUpdatePayload,
  shouldAutoAssignTherapists,
  type BookingFormInitial,
  type BookingFormValues,
} from "./booking-form.schema";
import { SHOP_TIMEZONE } from "@/shared/config/shop";
import {
  BookingBasicInfoRow,
  BookingCustomerRow,
  BookingCourseMatrix,
  BookingReservationEditor,
  BookingTherapistRow,
} from "./booking-form-sections";
import type { AdminBookingDetailRaw } from "../schedule.types";

const EMPTY_COURSES: CourseUiModel[] = [];
const EMPTY_THERAPISTS: TherapistUiModel[] = [];

export interface AvailabilityState {
  available: boolean;
  message?: string;
  reasonCode?: string;
  availableTherapistCount?: number;
  requiredTherapistCount?: number;
}

export interface BookingFormHandle {
  reset: () => void;
  checkAvailability: () => void;
}

export interface BookingFormSummary {
  bookingDate: string;
  startTime: string;
  numberOfPeople: number;
  durationMinutes: number;
  totalPrice: number;
}

interface BookingFormProps {
  initial: BookingFormInitial;
  onSaved: (bookingId: UUID) => void;
  onDirtyChange?: (dirty: boolean) => void;
  onAvailability?: (a: AvailabilityState | null) => void;
  onAvailabilityLoading?: (loading: boolean) => void;
  onSubmittingChange?: (submitting: boolean) => void;
  onSummaryChange?: (summary: BookingFormSummary) => void;
  editDetail?: AdminBookingDetailRaw;
}

// Quản lý toàn bộ state form tạo/chỉnh sửa, live checks, payload API và thông báo kết quả booking.
export const BookingForm = forwardRef<BookingFormHandle, BookingFormProps>(function BookingForm({
  initial,
  onSaved,
  onDirtyChange,
  onAvailability,
  onAvailabilityLoading,
  onSubmittingChange,
  onSummaryChange,
  editDetail,
}: BookingFormProps, ref) {
  const isEdit = initial.mode === "edit";
  const { showError, showSuccess } = useAlert();
  const groupMainCourseId = editDetail?.reservations[0]?.courses.find(
    (course) => course.course_role === "main",
  )?.course_id ?? "";
  const groupAddonCourseIds = editDetail?.reservations[0]?.courses
    .filter((course) => course.course_role === "addon")
    .map((course) => course.course_id) ?? [];

  const form = useForm<BookingFormValues>({
    resolver: zodResolver(isEdit ? bookingUpdateFormSchema : bookingFormSchema),
    defaultValues: {
      shopId: initial.shopId,
      bookingDate: initial.bookingDate,
      startTime: initial.startTime,
      numberOfPeople: initial.numberOfPeople ?? 1,
      customerPhone: initial.customerPhone ?? "",
      customerName: initial.customerName ?? "",
      mainCourseId: "",
      addonCourseIds: [],
      therapistRequestType: initial.therapistId ? "specific" : "none",
      requestedTherapistId: initial.therapistId ?? "",
      requestedGender: undefined,
      reservations: editDetail?.reservations.map((reservation) => ({
        reservationId: reservation.reservation_id,
        personIndex: reservation.person_index,
        therapistId: reservation.therapist.therapist_id,
        mainCourseId: groupMainCourseId,
        addonCourseIds: [...groupAddonCourseIds],
      })) ?? [],
      autoAssignTherapists: false,
    },
  });

  const { data: courseData } = useCourses(initial.shopId, { isActive: true });
  const { data: therapistData } = useTherapists(initial.shopId, true);
  const courses = courseData ?? EMPTY_COURSES;
  const therapists = therapistData ?? EMPTY_THERAPISTS;

  const createMut = useCreateBooking();
  const updateMut = useUpdateBooking(isEdit ? (initial.bookingId as UUID) : ("" as UUID));
  const eligibilityMut = useCheckEligibility();

  const [eligibility, setEligibility] = useState<EligibilityResult | null>(null);
  const [availability, setAvailability] = useState<AvailabilityState | null>(null);
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [availabilityRefreshToken, setAvailabilityRefreshToken] = useState(0);
  const bookingDate = form.watch("bookingDate");
  const startTime = form.watch("startTime");
  const numberOfPeople = form.watch("numberOfPeople");
  const mainCourseId = form.watch("mainCourseId");
  const addonCourseIds = form.watch("addonCourseIds");
  const reservationEdits = form.watch("reservations");
  const timezone = initial.timezone ?? SHOP_TIMEZONE;
  const minimumBookingAdvanceMinutes = initial.minimumBookingAdvanceMinutes ?? 15;
  // Tính thời lượng và tổng giá song song cho form tạo mới hoặc từng reservation khi chỉnh sửa.
  const summary = useMemo<BookingFormSummary>(() => {
    const selectedCourses = courses.filter(
      (course) => course.id === mainCourseId || addonCourseIds.includes(course.id),
    );
    // Tính duration/price riêng từng người trước khi tổng hợp booking nhóm.
    const editedPeople = reservationEdits.map((reservation) => {
      const selected = courses.filter(
        (course) => course.id === reservation.mainCourseId || reservation.addonCourseIds.includes(course.id),
      );
      return {
        duration: selected.reduce((total, course) => total + course.durationMinutes, 0),
        price: selected.reduce((total, course) => total + course.price, 0),
      };
    });
    return {
      bookingDate,
      startTime,
      numberOfPeople,
      durationMinutes: isEdit
        ? Math.max(0, ...editedPeople.map((person) => person.duration))
        : selectedCourses.reduce((total, course) => total + course.durationMinutes, 0),
      totalPrice: isEdit
        ? editedPeople.reduce((total, person) => total + person.price, 0)
        : selectedCourses.reduce((total, course) => total + course.price, 0),
    };
  }, [addonCourseIds, bookingDate, courses, isEdit, mainCourseId, numberOfPeople, reservationEdits, startTime]);
  const lastEmittedSummaryRef = useRef<BookingFormSummary | null>(null);

  useImperativeHandle(ref, () => ({
    reset: () => {
      form.reset();
      setEligibility(null);
      setAvailability(null);
      setAvailabilityLoading(false);
    },
    checkAvailability: () => setAvailabilityRefreshToken((token) => token + 1),
  }), [form]);

  const isDirty = form.formState.isDirty;
  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  // Propagate availability state to parent (BookingDrawer footer).
  useEffect(() => { onAvailability?.(availability); }, [availability, onAvailability]);
  useEffect(() => { onAvailabilityLoading?.(availabilityLoading); }, [availabilityLoading, onAvailabilityLoading]);
  useEffect(() => { onSubmittingChange?.(submitting); }, [onSubmittingChange, submitting]);
  useEffect(() => {
    const previous = lastEmittedSummaryRef.current;
    if (
      previous?.bookingDate === summary.bookingDate &&
      previous.startTime === summary.startTime &&
      previous.numberOfPeople === summary.numberOfPeople &&
      previous.durationMinutes === summary.durationMinutes &&
      previous.totalPrice === summary.totalPrice
    ) {
      return;
    }
    lastEmittedSummaryRef.current = summary;
    onSummaryChange?.(summary);
  }, [onSummaryChange, summary]);

  useEffect(() => {
    if (!isEdit) return;
    const current = form.getValues("reservations");
    const autoAssignTherapists = shouldAutoAssignTherapists(
      initial.numberOfPeople ?? 1,
      numberOfPeople,
    );
    if (form.getValues("autoAssignTherapists") !== autoAssignTherapists) {
      form.setValue("autoAssignTherapists", autoAssignTherapists, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
    // Sao chép reservation còn giữ lại để thay đổi số người mà không mutate state hiện tại.
    const next = current.slice(0, numberOfPeople).map((reservation) => ({
      ...reservation,
      addonCourseIds: [...reservation.addonCourseIds],
    }));
    const groupCourses = current[0] ?? {
      mainCourseId: "",
      addonCourseIds: [],
    };
    while (next.length < numberOfPeople) {
      next.push({
        reservationId: undefined,
        personIndex: next.length + 1,
        therapistId: "",
        mainCourseId: groupCourses.mainCourseId,
        addonCourseIds: [...groupCourses.addonCourseIds],
      });
    }
    if (autoAssignTherapists) {
      next.forEach((reservation) => {
        reservation.therapistId = "";
      });
    } else if (numberOfPeople === 1 && !next[0]?.therapistId) {
      next[0].therapistId = editDetail?.reservations[0]?.therapist.therapist_id ?? "";
    }
    const reservationsChanged =
      current.length !== next.length ||
      current.some((reservation, index) => reservation.therapistId !== next[index]?.therapistId);
    if (!reservationsChanged) return;
    form.setValue(
      "reservations",
      next.map((reservation, index) => ({ ...reservation, personIndex: index + 1 })),
      { shouldDirty: true, shouldValidate: true },
    );
  }, [editDetail?.reservations, form, initial.numberOfPeople, isEdit, numberOfPeople]);

  // Ánh xạ lỗi field vào React Hook Form và đưa lỗi nghiệp vụ/server lên alert dùng chung.
  const applyApiErrors = (err: unknown) => {
    if (err instanceof ApiError) {
      const fields = err.fieldErrors();
      for (const [field, message] of Object.entries(fields)) {
        form.setError(field as keyof BookingFormValues, { message });
      }
      if (err.code === "BOOKING_START_IN_PAST" || err.code === "BOOKING_START_TOO_SOON") {
        const message = err.detail || "Thời gian bắt đầu không còn hợp lệ.";
        setAvailability({ available: false, message });
        setAvailabilityRefreshToken((token) => token + 1);
      } else if (
        err.code === "SLOT_CONFLICT" ||
        err.code === "THERAPIST_NOT_AVAILABLE" ||
        err.code === "INSUFFICIENT_AVAILABLE_THERAPISTS" ||
        err.code === "OUTSIDE_SHIFT" ||
        err.code === "OUTSIDE_BUSINESS_HOURS" ||
        err.code === "GROUP_BOOKING_CANNOT_REQUEST_SPECIFIC_THERAPIST"
      ) {
        setAvailability({
          available: false,
          reasonCode: err.code,
          message: err.detail,
        });
      }
      const message = err.code === "CUSTOMER_IN_NG_LIST"
        ? "SĐT bị cấm đặt lịch (NG list)."
        : err.detail || err.body.title || "Lỗi khi lưu booking.";
      showError(message);
    } else {
      showError("Lỗi không xác định khi lưu booking.");
    }
  };

  // Chống gửi lặp, gọi mutation create/update, reset form và phát sự kiện lưu thành công.
  const onSubmit = form.handleSubmit(async (vals) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      if (isEdit && initial.bookingId) {
        await updateMut.mutateAsync(toUpdatePayload(vals));
        form.reset(vals);
        showSuccess("Cập nhật booking thành công.");
        onSaved(initial.bookingId);
      } else {
        const created = await createMut.mutateAsync(toCreatePayload(vals));
        form.reset(vals);
        showSuccess("Tạo booking thành công.");
        onSaved(created.booking_id);
      }
    } catch (err) {
      applyApiErrors(err);
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <FormProvider {...form}>
      <form id="booking-form" onSubmit={onSubmit} className="mx-auto w-full max-w-[1800px] space-y-0">
        {!isEdit && (
          <BookingLiveChecks
            form={form}
            shopId={initial.shopId}
            submitting={submitting}
            onEligibility={setEligibility}
            onAvailability={setAvailability}
            onAvailabilityLoading={setAvailabilityLoading}
            refreshToken={availabilityRefreshToken}
            timezone={timezone}
            minimumBookingAdvanceMinutes={minimumBookingAdvanceMinutes}
          />
        )}

        {/* Hàng 1: Ngày, giờ, số người */}
        <BookingBasicInfoRow
          bookingCode={isEdit ? initial.bookingId : undefined}
          numberOfPeopleReadOnly={false}
        />

        {isEdit && (
          <>
            <BookingCustomerRow
              eligibility={eligibility}
              eligibilityLoading={eligibilityMut.isPending}
              onCheck={() => {
                const phone = form.getValues("customerPhone");
                if (phone) {
                  eligibilityMut
                    .mutateAsync({ phone, shop_id: initial.shopId })
                    .then(setEligibility)
                    .catch(() => setEligibility(null));
                }
              }}
            />
            <BookingReservationEditor courses={courses} therapists={therapists} />
          </>
        )}

        {!isEdit && (
          <>
            {/* Hàng 2: Khách hàng */}
            <BookingCustomerRow
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

            {/* Hàng 3: Course matrix */}
            <BookingCourseMatrix courses={courses} />

            {/* Hàng 4: Therapist */}
            <BookingTherapistRow therapists={therapists} />
          </>
        )}
      </form>
    </FormProvider>
  );
});
