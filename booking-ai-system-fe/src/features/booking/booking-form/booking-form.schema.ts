import { z } from "zod";
import { GENDERS, THERAPIST_REQUEST_TYPES, type UUID } from "@/shared/types/common";

const reservationEditSchema = z.object({
  reservationId: z.string().optional(),
  personIndex: z.number().int().min(1).max(3),
  therapistId: z.string(),
  mainCourseId: z.string().min(1, "Chọn course chính cho người này"),
  addonCourseIds: z.array(z.string()),
});

const baseSchema = z.object({
  shopId: z.string().min(1, "Chọn shop"),
  bookingDate: z.string().min(1, "Chọn ngày"),
  startTime: z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Giờ không hợp lệ (HH:MM)"),
  numberOfPeople: z.number().int().min(1, "Tối thiểu 1 người").max(3, "Tối đa 3 người"),
  customerPhone: z.string().min(1, "Số điện thoại bắt buộc").regex(/^\+?\d{6,15}$/, "Số điện thoại không hợp lệ"),
  customerName: z.string().optional(),
  mainCourseId: z.string(),
  addonCourseIds: z.array(z.string()),
  therapistRequestType: z.enum(THERAPIST_REQUEST_TYPES),
  requestedTherapistId: z.string().optional(),
  requestedGender: z.enum(GENDERS).optional(),
  reservations: z.array(reservationEditSchema),
  autoAssignTherapists: z.boolean(),
});

// Kiểm tra chéo dữ liệu tạo booking, gồm course bắt buộc và điều kiện yêu cầu therapist theo loại booking.
export const bookingFormSchema = baseSchema.superRefine((values, ctx) => {
  if (!values.mainCourseId) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["mainCourseId"], message: "Chọn ít nhất 1 course chính" });
  }
  if (values.therapistRequestType === "specific" && !values.requestedTherapistId) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["requestedTherapistId"], message: "Chọn therapist cụ thể" });
  }
  if (values.numberOfPeople > 1 && values.therapistRequestType === "specific") {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["therapistRequestType"], message: "Booking nhóm không được chọn một therapist cụ thể" });
  }
  if (values.therapistRequestType === "gender" && !values.requestedGender) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["requestedGender"], message: "Chọn giới tính therapist" });
  }
});

// Kiểm tra chéo dữ liệu chỉnh sửa để số người, therapist và bộ course của booking nhóm luôn nhất quán.
export const bookingUpdateFormSchema = baseSchema.superRefine((values, ctx) => {
  if (values.reservations.length !== values.numberOfPeople) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["reservations"], message: "Số reservation phải bằng số người" });
  }
  // Thu therapist ID của từng người để kiểm tra thiếu hoặc phân công trùng trong nhóm.
  const therapistIds = values.reservations.map((item) => item.therapistId);
  if (values.autoAssignTherapists && therapistIds.some(Boolean)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["reservations"], message: "Không được chỉ định therapist khi chuyển sang booking nhóm" });
  }
  if (!values.autoAssignTherapists && therapistIds.some((therapistId) => !therapistId)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["reservations"], message: "Mỗi người phải có therapist" });
  }
  const assignedTherapistIds = therapistIds.filter(Boolean);
  if (new Set(assignedTherapistIds).size !== assignedTherapistIds.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["reservations"], message: "Mỗi người phải có therapist khác nhau" });
  }
  // Chuẩn hóa lựa chọn course thành signature để bảo đảm mọi người trong nhóm dùng cùng dịch vụ.
  const courseSignatures = values.reservations.map((reservation) =>
    JSON.stringify([
      reservation.mainCourseId,
      ...[...reservation.addonCourseIds].sort(),
    ]),
  );
  if (courseSignatures.length > 1 && courseSignatures.some((signature) => signature !== courseSignatures[0])) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["reservations"],
      message: "Course chính và course thêm phải giống nhau cho cả nhóm",
    });
  }
});

export type BookingFormValues = z.infer<typeof baseSchema>;

// Xác định trường hợp chuyển booking một người thành nhóm để backend tự động phân công therapist.
export function shouldAutoAssignTherapists(
  originalNumberOfPeople: number,
  nextNumberOfPeople: number,
) {
  return originalNumberOfPeople === 1 && nextNumberOfPeople > 1;
}

export interface BookingFormInitial {
  mode: "create" | "edit";
  shopId: UUID;
  bookingDate: string;
  startTime: string;
  therapistId?: UUID;
  bookingId?: UUID;
  customerPhone?: string;
  customerName?: string;
  numberOfPeople?: number;
  durationMinutes?: number;
  totalPrice?: number;
  timezone?: string;
  minimumBookingAdvanceMinutes?: number;
}

export interface CreateBookingPayload {
  shop_id: UUID;
  booking_date: string;
  start_time: string;
  number_of_people: number;
  customer: { phone: string; name: string | null };
  courses: Array<{ course_id: UUID; course_role: "main" | "addon" }>;
  therapist_request: { type: "none" | "specific" | "gender"; therapist_id?: UUID; gender?: "male" | "female" };
  confirmed_by_customer: boolean;
}

// Chuyển form tạo mới sang payload API và vô hiệu hóa yêu cầu specific đối với booking nhóm.
export function toCreatePayload(values: BookingFormValues): CreateBookingPayload {
  const effectiveType = values.numberOfPeople > 1 && values.therapistRequestType === "specific" ? "none" : values.therapistRequestType;
  const therapistRequest: CreateBookingPayload["therapist_request"] = { type: effectiveType };
  if (effectiveType === "specific" && values.requestedTherapistId) therapistRequest.therapist_id = values.requestedTherapistId as UUID;
  if (effectiveType === "gender" && values.requestedGender) therapistRequest.gender = values.requestedGender;
  return {
    shop_id: values.shopId as UUID,
    booking_date: values.bookingDate,
    start_time: values.startTime,
    number_of_people: values.numberOfPeople,
    customer: { phone: values.customerPhone, name: values.customerName?.trim() || null },
    courses: [
      { course_id: values.mainCourseId as UUID, course_role: "main" },
      ...values.addonCourseIds.map((courseId) => ({ course_id: courseId as UUID, course_role: "addon" as const })),
    ],
    therapist_request: therapistRequest,
    confirmed_by_customer: true,
  };
}

export interface UpdateBookingPayload {
  booking_date: string;
  start_time: string;
  customer: { phone: string; name: string | null };
  reservations: Array<{
    reservation_id?: UUID;
    person_index: number;
    therapist_id?: UUID;
    courses: Array<{ course_id: UUID; course_role: "main" | "addon" }>;
  }>;
  auto_assign_therapists: boolean;
}

// Chuyển form chỉnh sửa thành payload theo reservation để backend cập nhật đúng từng người.
export function toUpdatePayload(values: BookingFormValues): UpdateBookingPayload {
  return {
    booking_date: values.bookingDate,
    start_time: values.startTime,
    customer: { phone: values.customerPhone, name: values.customerName?.trim() || null },
    reservations: values.reservations.map((reservation) => ({
      ...(reservation.reservationId ? { reservation_id: reservation.reservationId as UUID } : {}),
      person_index: reservation.personIndex,
      ...(reservation.therapistId ? { therapist_id: reservation.therapistId as UUID } : {}),
      courses: [
        { course_id: reservation.mainCourseId as UUID, course_role: "main" as const },
        ...reservation.addonCourseIds.map((courseId) => ({ course_id: courseId as UUID, course_role: "addon" as const })),
      ],
    })),
    auto_assign_therapists: values.autoAssignTherapists,
  };
}
