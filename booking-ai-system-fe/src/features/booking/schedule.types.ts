// Raw backend DTO (theo admin/bookings.py, therapist_shifts.py và các query/schedule service).
import type { UUID, ISOTime, ISODate, BookingStatus } from "@/shared/types/common";

// --- Shift (therapist_shifts) ---
export interface ShiftRaw {
  shift_id: UUID;
  shop_id: UUID;
  therapist_id: UUID;
  work_date: ISODate;
  start_time: ISOTime;
  end_time: ISOTime;
  is_active: boolean;
}

// --- Booking list item (admin) ---
export interface AdminBookingListItemRaw {
  booking_id: UUID;
  pos_booking_code: string | null;
  shop_id: UUID;
  customer: { customer_id: UUID; phone: string; name: string | null } | null;
  booking_date: ISODate;
  start_time: ISOTime;
  end_time: ISOTime;
  number_of_people: number;
  status: BookingStatus;
}

// --- Booking detail (admin) — để lấy reservation.therapist_id ---
export interface AdminBookingDetailRaw {
  booking_id: UUID;
  pos_booking_code: string | null;
  status: BookingStatus;
  shop: { shop_id: UUID | null; name: string | null };
  booking_date: ISODate;
  start_time: ISOTime;
  end_time: ISOTime;
  number_of_people: number;
  total_duration_minutes: number;
  customer: {
    customer_id: UUID | null;
    name: string | null;
    phone: string | null;
    is_member: boolean;
    member_rank: string | null;
    visit_count: number;
  } | null;
  reservations: Array<{
    reservation_id: UUID;
    person_index: number;
    therapist: { therapist_id: UUID; name: string | null };
    courses: Array<{
      course_id: UUID;
      course_name_snapshot: string;
      course_role: string;
      duration_snapshot: number;
      price_snapshot: number;
    }>;
  }>;
}

// --- View models cho timeline (nguyên tắc 6: không đẩy raw vào UI) ---
export interface ResourceViewModel {
  therapistId: UUID;
  name: string;
  // Ca làm việc (có thể nhiều ca / ngày)
  shifts: ShiftViewModel[];
}

export interface ShiftViewModel {
  id: UUID;
  startMinutes: number; // phút tuyệt đối (đã xử lý qua nửa đêm)
  endMinutes: number;
  isActive: boolean;
}

export type BookingStatusToken = "confirmed" | "pending" | "checked-in" | "completed" | "cancelled" | "other";

export interface BookingViewModel {
  bookingId: UUID;
  reservationId: UUID;
  bookingDate: ISODate;
  therapistId: UUID;
  therapistName: string | null;
  startMinutes: number; // phút tuyệt đối trên timeline
  endMinutes: number;
  status: BookingStatusToken;
  customerName: string | null;
  customerPhone: string;
  courseNames: string[];
  posCode: string | null;
}

export interface ScheduleViewModel {
  resources: ResourceViewModel[];
  bookings: BookingViewModel[];
  date: ISODate;
  timezone: string;
  minimumBookingAdvanceMinutes: number;
  therapistBreakMinutes: number;
  // Khoảng hiển thị tính bằng phút tuyệt đối
  timelineStartMinutes: number;
  timelineEndMinutes: number;
}
