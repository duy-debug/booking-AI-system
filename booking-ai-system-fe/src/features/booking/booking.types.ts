import type {
  BookingStatus,
  DecimalString,
  ISOTime,
  ISODate,
  UUID,
} from "@/shared/types/common";

// --- Raw backend DTO (theo app/services/booking_service.py:155-173) ---
export interface ReservationCourseRaw {
  course_id: UUID;
  course_role: "main" | "addon";
  course_name_snapshot: string;
  duration_snapshot: number;
  price_snapshot: DecimalString; // string tại public endpoint
}

export interface ReservationRaw {
  reservation_id: UUID;
  person_index: number;
  therapist_id: UUID;
  start_time: ISOTime;
  end_time: ISOTime;
  status: string;
  courses: ReservationCourseRaw[];
}

export interface BookingDetailRaw {
  booking_id: UUID;
  shop_id: UUID;
  customer_id: UUID;
  booking_date: ISODate;
  start_time: ISOTime;
  end_time: ISOTime;
  number_of_people: number;
  total_duration_minutes: number;
  status: BookingStatus;
  therapist_request_type: "none" | "specific" | "gender";
  requested_therapist_id: UUID | null;
  requested_gender: "male" | "female" | null;
  cancel_reason: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  reservations: ReservationRaw[];
}

export interface BookingListItemRaw {
  booking_id: UUID;
  shop_id: UUID;
  booking_date: ISODate;
  start_time: ISOTime;
  end_time: ISOTime;
  number_of_people: number;
  total_duration_minutes: number;
  status: BookingStatus;
}

export interface AdminBookingListItemRaw {
  booking_id: UUID;
  pos_booking_code: string | null;
  shop_id: UUID;
  customer: {
    customer_id: UUID;
    phone: string;
    name: string | null;
  } | null;
  booking_date: ISODate;
  start_time: ISOTime;
  end_time: ISOTime;
  number_of_people: number;
  status: BookingStatus;
}

// --- UI models (đã normalize: Decimal->number, endDate qua nửa đêm) ---
export interface ReservationCourseUi {
  courseId: UUID;
  courseRole: "main" | "addon";
  courseName: string;
  durationMinutes: number;
  price: number;
}

export interface ReservationUi {
  reservationId: UUID;
  personIndex: number;
  therapistId: UUID;
  startTime: ISOTime;
  endTime: ISOTime;
  status: string;
  courses: ReservationCourseUi[];
}

export interface BookingDetailUi {
  id: UUID;
  shopId: UUID;
  customerId: UUID;
  bookingDate: ISODate;
  endDate: ISODate; // đã tính qua nửa đêm
  startTime: ISOTime;
  endTime: ISOTime;
  numberOfPeople: number;
  totalDurationMinutes: number;
  status: BookingStatus;
  therapistRequestType: "none" | "specific" | "gender";
  requestedTherapistId: UUID | null;
  requestedGender: "male" | "female" | null;
  cancelReason: string | null;
  cancelledAt: string | null;
  createdAt: string;
  updatedAt: string;
  reservations: ReservationUi[];
}

// --- Mappers ---
import { resolveEndDate, parseDecimal } from "@/shared/lib/datetime";

export function toBookingDetailUi(raw: BookingDetailRaw): BookingDetailUi {
  return {
    id: raw.booking_id,
    shopId: raw.shop_id,
    customerId: raw.customer_id,
    bookingDate: raw.booking_date,
    endDate: resolveEndDate(raw.booking_date, raw.start_time, raw.end_time),
    startTime: raw.start_time,
    endTime: raw.end_time,
    numberOfPeople: raw.number_of_people,
    totalDurationMinutes: raw.total_duration_minutes,
    status: raw.status,
    therapistRequestType: raw.therapist_request_type,
    requestedTherapistId: raw.requested_therapist_id,
    requestedGender: raw.requested_gender,
    cancelReason: raw.cancel_reason,
    cancelledAt: raw.cancelled_at,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    reservations: raw.reservations.map((r) => ({
      reservationId: r.reservation_id,
      personIndex: r.person_index,
      therapistId: r.therapist_id,
      startTime: r.start_time,
      endTime: r.end_time,
      status: r.status,
      courses: r.courses.map((c) => ({
        courseId: c.course_id,
        courseRole: c.course_role,
        courseName: c.course_name_snapshot,
        durationMinutes: c.duration_snapshot,
        price: parseDecimal(c.price_snapshot),
      })),
    })),
  };
}

export interface BookingListUi {
  id: UUID;
  shopId: UUID;
  bookingDate: ISODate;
  endDate: ISODate;
  startTime: ISOTime;
  endTime: ISOTime;
  numberOfPeople: number;
  totalDurationMinutes: number;
  status: BookingStatus;
}

export function toBookingListUi(raw: AdminBookingListItemRaw): BookingListUi {
  return {
    id: raw.booking_id,
    shopId: raw.shop_id,
    bookingDate: raw.booking_date,
    endDate: resolveEndDate(raw.booking_date, raw.start_time, raw.end_time),
    startTime: raw.start_time,
    endTime: raw.end_time,
    numberOfPeople: raw.number_of_people,
    totalDurationMinutes: 0,
    status: raw.status,
  };
}

// --- API paths ---
export const bookingApi = {
  list: "/api/admin/bookings",
  detail: (id: UUID) => `/api/admin/bookings/${id}`,
  cancel: (id: UUID) => `/api/admin/bookings/${id}`,
};
