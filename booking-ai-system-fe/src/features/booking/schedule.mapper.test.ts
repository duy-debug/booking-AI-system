import { describe, it, expect } from "vitest";
import { toScheduleViewModel } from "./schedule.mapper";
import { buildTimelineRange } from "./schedule.utils";
import { BUSINESS_HOURS } from "@/shared/config/shop";
import type { ScheduleResponseRaw } from "./schedule.api";

const range = buildTimelineRange(BUSINESS_HOURS.open, BUSINESS_HOURS.close); // 09:00 - 22:00

const raw: ScheduleResponseRaw = {
  shop: {
    shop_id: "shop1",
    name: "Shop A",
    timezone: "Asia/Ho_Chi_Minh",
    business_hours: { open: "09:00", close: "22:00", spans_midnight: false },
  },
  date: "2026-07-20",
  view_window: { from: "09:00", to: "22:00", spans_midnight: false },
  therapists: [
    { therapist_id: "t1", name: "Therapist A", gender: "female", is_active: true },
  ],
  shifts: [
    {
      shift_id: "s1",
      therapist_id: "t1",
      therapist_name: "Therapist A",
      start_time: "09:00",
      end_time: "17:00",
      is_active: true,
      spans_midnight: false,
    },
  ],
  blocked_ranges: [],
  bookings: [
    {
      booking_id: "b1",
      pos_booking_code: "POS1",
      customer: { customer_id: "c1", phone: "0901", name: "Nguyen" },
      booking_date: "2026-07-20",
      start_time: "10:00",
      end_time: "11:30",
      status: "confirmed",
      number_of_people: 1,
      total_duration_minutes: 90,
      therapist_request_type: "none",
      requested_therapist_id: null,
      spans_midnight: false,
      reservations: [
        {
          reservation_id: "r1",
          person_index: 0,
          therapist_id: "t1",
          therapist_name: "Therapist A",
          start_time: "10:00",
          end_time: "11:30",
          status: "assigned",
          spans_midnight: false,
          courses: [{ course_role: "main", course_name_snapshot: "Massage", duration_snapshot: 90, price_snapshot: 300 }],
        },
      ],
    },
  ],
  booking_statuses: ["confirmed"],
};

describe("toScheduleViewModel", () => {
  it("map shift thành absolute minutes", () => {
    const vm = toScheduleViewModel(raw, range);
    expect(vm.resources).toHaveLength(1);
    expect(vm.resources[0].therapistId).toBe("t1");
    expect(vm.resources[0].shifts[0].startMinutes).toBe(540); // 09:00
    expect(vm.resources[0].shifts[0].endMinutes).toBe(1020); // 17:00
  });

  it("map booking reservation sang BookingViewModel với therapist + absolute minutes", () => {
    const vm = toScheduleViewModel(raw, range);
    expect(vm.bookings).toHaveLength(1);
    const b = vm.bookings[0];
    expect(b.therapistId).toBe("t1");
    expect(b.startMinutes).toBe(600); // 10:00
    expect(b.endMinutes).toBe(690); // 11:30
    expect(b.status).toBe("confirmed");
    expect(b.customerName).toBe("Nguyen");
    expect(b.courseNames).toEqual(["Massage"]);
    expect(b.posCode).toBe("POS1");
  });

  it("xử lý booking qua nửa đêm: 23:00 -> 01:30 thành 1410 -> 1530", () => {
    const overnight: ScheduleResponseRaw = {
      ...raw,
      bookings: [
        {
          ...raw.bookings[0],
          booking_id: "b2",
          start_time: "23:00",
          end_time: "01:30",
          spans_midnight: true,
          reservations: [
            {
              ...raw.bookings[0].reservations[0],
              reservation_id: "r2",
              start_time: "23:00",
              end_time: "01:30",
              spans_midnight: true,
            },
          ],
        },
      ],
    };
    const overnightRange = buildTimelineRange("09:00", "05:00");
    const vm = toScheduleViewModel(overnight, overnightRange);
    expect(vm.bookings[0].startMinutes).toBe(1380); // 23:00
    expect(vm.bookings[0].endMinutes).toBe(1530); // 01:30 hôm sau
  });

  it("status token cho cancelled", () => {
    const cancelled: ScheduleResponseRaw = {
      ...raw,
      bookings: [
        { ...raw.bookings[0], booking_id: "b3", status: "cancelled" },
      ],
    };
    const vm = toScheduleViewModel(cancelled, range);
    expect(vm.bookings[0].status).toBe("cancelled");
  });

  it("tạo resource mới nếu booking có therapist chưa có trong shifts", () => {
    const extra: ScheduleResponseRaw = {
      ...raw,
      therapists: [...raw.therapists, { therapist_id: "tX", name: "Therapist X", gender: "male", is_active: true }],
      bookings: [
        {
          ...raw.bookings[0],
          booking_id: "b4",
          start_time: "14:00",
          end_time: "15:00",
          reservations: [
            {
              ...raw.bookings[0].reservations[0],
              reservation_id: "r4",
              therapist_id: "tX",
              therapist_name: "Therapist X",
              start_time: "14:00",
              end_time: "15:00",
            },
          ],
        },
      ],
    };
    const vm = toScheduleViewModel(extra, range);
    expect(vm.resources.some((r) => r.therapistId === "tX")).toBe(true);
  });
});
