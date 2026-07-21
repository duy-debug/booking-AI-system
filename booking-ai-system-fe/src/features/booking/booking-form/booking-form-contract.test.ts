import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { toCreatePayload, type BookingFormValues } from "./booking-form.schema";

describe("booking form backend contract", () => {
  it("creates a payload containing only backend-supported fields", () => {
    const values: BookingFormValues = {
      shopId: "shop-id",
      bookingDate: "2026-07-21",
      startTime: "10:30",
      numberOfPeople: 1,
      customerPhone: "0901234567",
      customerName: "Nguyễn An",
      mainCourseId: "main-60",
      addonCourseIds: ["addon-15"],
      therapistRequestType: "specific",
      requestedTherapistId: "therapist-id",
      requestedGender: undefined,
    };

    expect(toCreatePayload(values)).toEqual({
      shop_id: "shop-id",
      booking_date: "2026-07-21",
      start_time: "10:30",
      number_of_people: 1,
      customer: { phone: "0901234567", name: "Nguyễn An" },
      courses: [
        { course_id: "main-60", course_role: "main" },
        { course_id: "addon-15", course_role: "addon" },
      ],
      therapist_request: { type: "specific", therapist_id: "therapist-id" },
      confirmed_by_customer: true,
    });
  });

  it("does not render controls for fields missing from the backend contract", () => {
    const source = readFileSync(
      join(process.cwd(), "src/features/booking/booking-form/booking-form-sections.tsx"),
      "utf8",
    );
    const unsupportedLabels = [
      "Mã thành viên",
      "Ngày sinh",
      "Giới tính khách",
      "Vị trí đau",
      "Không được chạm",
      "Nguồn booking",
      "Khoảng nghỉ",
      "Mức trò chuyện",
      "Lực massage",
      "Thay đồ",
      "Ghi chú",
    ];

    for (const label of unsupportedLabels) {
      expect(source).not.toContain(`>${label}<`);
    }
  });
});
