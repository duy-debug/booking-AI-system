import { z } from "zod";
import {
  THERAPIST_REQUEST_TYPES,
  GENDERS,
  type UUID,
} from "@/shared/types/common";

// Schema form cho Booking Drawer.
// CHỈ chứa field backend thực sự hỗ trợ (docs/frontend-analysis.md §3.7).
// Các field giao diện cũ chưa có DB nằm ở docs/missing-booking-fields.md.

export const bookingFormSchema = z
  .object({
    // 1. BookingTimeSection
    shopId: z.string().min(1, "Chọn shop"),
    bookingDate: z.string().min(1, "Chọn ngày"),
    startTime: z
      .string()
      .regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Giờ không hợp lệ (HH:MM)"),
    numberOfPeople: z
      .number()
      .int()
      .min(1, "Tối thiểu 1 người")
      .max(3, "Tối đa 3 người"),

    // 2. CustomerSection
    customerPhone: z
      .string()
      .min(1, "Số điện thoại bắt buộc")
      .regex(/^\+?\d{6,15}$/, "Số điện thoại không hợp lệ"),
    customerName: z.string().optional(),

    // 3. CourseSection
    mainCourseId: z.string().min(1, "Chọn ít nhất 1 course chính"),
    addonCourseIds: z.array(z.string()),

    // 5. TherapistSection (therapist_request)
    therapistRequestType: z.enum(THERAPIST_REQUEST_TYPES),
    requestedTherapistId: z.string().optional(),
    requestedGender: z.enum(GENDERS).optional(),

    // 4/6..10: field chưa có backend -> không nằm trong payload.
    // Giữ ở form state để người dùng thấy, nhưng KHÔNG gửi lên (xem missing doc).
    // (các field này optional, không nằm trong toCreatePayload)
  })
  .superRefine((val, ctx) => {
    // Nếu yêu cầu therapist cụ thể mà chưa chọn -> lỗi
    if (val.therapistRequestType === "specific" && !val.requestedTherapistId) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["requestedTherapistId"],
        message: "Chọn therapist cụ thể",
      });
    }
    // Nhóm (>1 người) KHÔNG được yêu cầu therapist cụ thể (backend 422)
    if (
      val.numberOfPeople > 1 &&
      val.therapistRequestType === "specific"
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["therapistRequestType"],
        message: "Booking nhóm không được chọn therapist cụ thể",
      });
    }
    if (val.therapistRequestType === "gender" && !val.requestedGender) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["requestedGender"],
        message: "Chọn giới tính therapist",
      });
    }
  });

export type BookingFormValues = z.infer<typeof bookingFormSchema>;

export interface BookingFormInitial {
  mode: "create" | "edit";
  shopId: UUID;
  bookingDate: string; // YYYY-MM-DD
  startTime: string; // HH:MM
  therapistId?: UUID; // từ selection / reservation
  bookingId?: UUID; // edit mode
  customerPhone?: string;
  customerName?: string;
}

// Payload tạo booking gửi lên POST /api/bookings (docs §3.7).
// KHÔNG chứa field nào backend chưa có.
export interface CreateBookingPayload {
  shop_id: UUID;
  booking_date: string;
  start_time: string;
  number_of_people: number;
  customer: { phone: string; name: string | null };
  courses: Array<{ course_id: UUID; course_role: "main" | "addon" }>;
  therapist_request: {
    type: "none" | "specific" | "gender";
    therapist_id?: UUID;
    gender?: "male" | "female";
  };
  confirmed_by_customer: boolean;
}

export function toCreatePayload(values: BookingFormValues): CreateBookingPayload {
  const courses = [
    { course_id: values.mainCourseId as UUID, course_role: "main" as const },
    ...values.addonCourseIds.map((id) => ({
      course_id: id as UUID,
      course_role: "addon" as const,
    })),
  ];

  const therapistRequest: CreateBookingPayload["therapist_request"] = {
    type: values.therapistRequestType,
  };
  if (values.therapistRequestType === "specific" && values.requestedTherapistId) {
    therapistRequest.therapist_id = values.requestedTherapistId as UUID;
  }
  if (values.therapistRequestType === "gender" && values.requestedGender) {
    therapistRequest.gender = values.requestedGender;
  }

  return {
    shop_id: values.shopId as UUID,
    booking_date: values.bookingDate,
    start_time: values.startTime,
    number_of_people: values.numberOfPeople,
    customer: {
      phone: values.customerPhone,
      name: values.customerName?.trim() ? values.customerName.trim() : null,
    },
    courses,
    therapist_request: therapistRequest,
    confirmed_by_customer: true,
  };
}

// PATCH chỉ cho phép sửa booking_date / start_time (docs §3.7, §4.6).
export interface UpdateBookingPayload {
  booking_date: string;
  start_time: string;
}

export function toUpdatePayload(values: BookingFormValues): UpdateBookingPayload {
  return {
    booking_date: values.bookingDate,
    start_time: values.startTime,
  };
}
