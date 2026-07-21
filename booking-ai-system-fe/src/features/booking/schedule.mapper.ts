import {
  toAbsoluteMinutes,
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

function statusToken(status: string): BookingStatusToken {
  if (status === "confirmed") return "confirmed";
  if (status === "cancelled") return "cancelled";
  return "other";
}

// Map response tổng hợp GET /api/admin/schedule -> ScheduleViewModel.
// Không còn N+1: reservation.therapist_id + courses đã có sẵn trong 1 request.
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
      startMinutes: toAbsoluteMinutes(s.start_time, timeline.start),
      endMinutes: toAbsoluteMinutes(s.end_time, timeline.start),
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
        startMinutes: toAbsoluteMinutes(res.start_time, timeline.start),
        endMinutes: toAbsoluteMinutes(res.end_time, timeline.start),
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
    timelineStartMinutes: timeline.start,
    timelineEndMinutes: timeline.end,
  };
}
