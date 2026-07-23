// Raw DTO cho endpoint tổng hợp GET /api/admin/schedule (1 request thay N+1).
// Căn cứ: app/api/admin/schedule.py, app/services/schedule_service.py.
import type { UUID, ISODate, BookingStatus } from "@/shared/types/common";

export interface ScheduleShopRaw {
  shop_id: UUID;
  name: string;
  timezone: string;
  minimum_booking_advance_minutes: number;
  therapist_break_minutes?: number;
  business_hours: {
    open: string;
    close: string;
    spans_midnight: boolean;
  };
}

export interface ScheduleTherapistRaw {
  therapist_id: UUID;
  name: string | null;
  gender: "male" | "female" | null;
  is_active: boolean;
}

export interface ScheduleShiftRaw {
  shift_id: UUID;
  therapist_id: UUID;
  therapist_name: string | null;
  start_time: string; // HH:MM
  end_time: string; // HH:MM
  is_active: boolean;
  spans_midnight: boolean;
}

export interface ScheduleBlockedRangeRaw {
  therapist_id: UUID;
  therapist_name: string | null;
  start_time: string;
  end_time: string;
  spans_midnight: boolean;
  reason: string | null;
}

export interface ScheduleReservationRaw {
  reservation_id: UUID;
  person_index: number;
  therapist_id: UUID;
  therapist_name: string | null;
  start_time: string;
  end_time: string;
  status: string;
  spans_midnight: boolean;
  courses: Array<{
    course_role: string;
    course_name_snapshot: string;
    duration_snapshot: number | null;
    price_snapshot: number;
  }>;
}

export interface ScheduleBookingRaw {
  booking_id: UUID;
  pos_booking_code: string | null;
  customer: {
    customer_id: UUID | null;
    phone: string | null;
    name: string | null;
  } | null;
  booking_date: ISODate;
  start_time: string;
  end_time: string;
  status: BookingStatus;
  number_of_people: number;
  total_duration_minutes: number | null;
  therapist_request_type: string;
  requested_therapist_id: UUID | null;
  spans_midnight: boolean;
  reservations: ScheduleReservationRaw[];
}

export interface ScheduleResponseRaw {
  shop: ScheduleShopRaw;
  date: ISODate;
  view_window: {
    from: string;
    to: string;
    spans_midnight: boolean;
  };
  therapists: ScheduleTherapistRaw[];
  shifts: ScheduleShiftRaw[];
  blocked_ranges: ScheduleBlockedRangeRaw[];
  bookings: ScheduleBookingRaw[];
  booking_statuses: string[];
}
