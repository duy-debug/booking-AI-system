import {
  parseTimeToMinutes,
  toOvernightEndMinutes,
  type TimeRange,
} from "./schedule.utils";
import type {
  BookingStatusToken,
  BookingViewModel,
  ResourceViewModel,
  ScheduleViewModel,
} from "./schedule.types";
import type {
  ScheduleResponseRaw,
  ScheduleShiftRaw,
  ScheduleBookingRaw,
} from "./schedule.api";

// Chuẩn hóa status backend về tập token giới hạn mà timeline biết cách hiển thị.
function statusToken(status: string): BookingStatusToken {
  if (status === "confirmed") return "confirmed";
  if (status === "pending") return "pending";
  if (status === "checked-in" || status === "checked_in") return "checked-in";
  if (status === "completed") return "completed";
  if (status === "cancelled") return "cancelled";
  return "other";
}

// Chuyển giờ bắt đầu shift sang phút tuyệt đối theo cửa sổ timeline có thể qua nửa đêm.
function toShiftStartMinutes(startTime: string, spansMidnight: boolean): number {
  return spansMidnight ? parseTimeToMinutes(startTime) : parseTimeToMinutes(startTime);
}

// Chuyển giờ kết thúc shift sang phút tuyệt đối và cộng một ngày khi shift qua nửa đêm.
function toShiftEndMinutes(endTime: string, spansMidnight: boolean): number {
  if (spansMidnight) return toOvernightEndMinutes(endTime);
  return parseTimeToMinutes(endTime);
}

// Map response tổng hợp GET /api/admin/schedule -> ScheduleViewModel.
export function toScheduleViewModel(
  raw: ScheduleResponseRaw,
  timeline: TimeRange,
): ScheduleViewModel {
  const date = raw.date;
  const shiftsByTherapist = new Map<string, ResourceViewModel["shifts"]>();
  const therapistOrder: string[] = [];
  const therapistName = new Map<string, string>();

  for (const t of raw.therapists) {
    if (!therapistOrder.includes(t.therapist_id)) therapistOrder.push(t.therapist_id);
    if (t.name) therapistName.set(t.therapist_id, t.name);
  }

  for (const s of raw.shifts as ScheduleShiftRaw[]) {
    const tid = s.therapist_id;
    if (!shiftsByTherapist.has(tid)) {
      shiftsByTherapist.set(tid, []);
      if (!therapistOrder.includes(tid)) therapistOrder.push(tid);
    }
    if (s.therapist_name) therapistName.set(tid, s.therapist_name);
    shiftsByTherapist.get(tid)!.push({
      id: s.shift_id,
      startMinutes: toShiftStartMinutes(s.start_time, s.spans_midnight),
      endMinutes: toShiftEndMinutes(s.end_time, s.spans_midnight),
      isActive: s.is_active,
    });
  }

  const bookingViewModels: BookingViewModel[] = [];
  for (const b of raw.bookings as ScheduleBookingRaw[]) {
    for (const res of b.reservations) {
      const tid = res.therapist_id;
      if (!shiftsByTherapist.has(tid)) {
        shiftsByTherapist.set(tid, []);
        if (!therapistOrder.includes(tid)) therapistOrder.push(tid);
      }
      if (res.therapist_name) therapistName.set(tid, res.therapist_name);
      bookingViewModels.push({
        bookingId: b.booking_id,
        reservationId: res.reservation_id,
        bookingDate: b.booking_date,
        therapistId: tid,
        therapistName: res.therapist_name ?? therapistName.get(tid) ?? null,
        startMinutes: toShiftStartMinutes(res.start_time, res.spans_midnight),
        endMinutes: toShiftEndMinutes(res.end_time, res.spans_midnight),
        status: statusToken(b.status),
        customerName: b.customer?.name ?? null,
        customerPhone: b.customer?.phone ?? "",
        courseNames: res.courses.map((c) => c.course_name_snapshot),
        posCode: b.pos_booking_code,
      });
    }
  }

  const resources: ResourceViewModel[] = therapistOrder.map((tid) => ({
    therapistId: tid,
    name: therapistName.get(tid) ?? "Therapist",
    shifts: shiftsByTherapist.get(tid) ?? [],
  }));

  return {
    resources,
    bookings: bookingViewModels,
    date,
    timezone: raw.shop.timezone,
    minimumBookingAdvanceMinutes: raw.shop.minimum_booking_advance_minutes ?? 15,
    therapistBreakMinutes: raw.shop.therapist_break_minutes ?? 0,
    timelineStartMinutes: timeline.start,
    timelineEndMinutes: timeline.end,
  };
}
