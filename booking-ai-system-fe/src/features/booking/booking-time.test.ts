import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { BUSINESS_HOURS } from "@/shared/config/shop";
import {
  earliestSelectableForDate,
  validateBookingStart,
} from "./booking-time";

const now = new Date("2026-07-21T02:00:00.000Z");

describe("booking start rules", () => {
  it.each([
    [119, "BOOKING_START_IN_PAST"],
    [120, "BOOKING_START_TOO_SOON"],
    [134, "BOOKING_START_TOO_SOON"],
  ] as const)("rejects minute %i with %s", (startMinutes, code) => {
    expect(validateBookingStart({
      bookingDate: "2026-07-21",
      startMinutes,
      timeZone: "UTC",
      now,
    }).code).toBe(code);
  });

  it.each([135, 136])("allows minute %i", (startMinutes) => {
    expect(validateBookingStart({
      bookingDate: "2026-07-21",
      startMinutes,
      timeZone: "UTC",
      now,
    }).valid).toBe(true);
  });

  it("allows future dates without a current-time cutoff", () => {
    expect(earliestSelectableForDate({
      bookingDate: "2026-07-22",
      stepMinutes: 15,
      timeZone: "UTC",
      now,
    })).toBeNull();
  });

  it("disables every slot on a past date", () => {
    expect(earliestSelectableForDate({
      bookingDate: "2026-07-20",
      stepMinutes: 15,
      timeZone: "UTC",
      now,
    })).toBe(Number.POSITIVE_INFINITY);
  });

  it("ceilToStep includes seconds", () => {
    expect(earliestSelectableForDate({
      bookingDate: "2026-07-21",
      stepMinutes: 15,
      timeZone: "UTC",
      now: new Date("2026-07-21T02:00:01.000Z"),
    })).toBe(150);
  });

  it("uses the shop timezone rather than the machine timezone", () => {
    expect(validateBookingStart({
      bookingDate: "2026-07-21",
      startMinutes: 11 * 60 + 14,
      timeZone: "Asia/Tokyo",
      now,
    }).code).toBe("BOOKING_START_TOO_SOON");
  });

  it("covers every selectable start time in a 24-hour day", () => {
    expect(BUSINESS_HOURS).toEqual({ open: "00:00", close: "23:45" });
  });

  it("shows a shared alert and refreshes availability when backend rejects a stale slot", () => {
    const source = readFileSync(
      join(process.cwd(), "src/features/booking/booking-form/BookingForm.tsx"),
      "utf8",
    );
    expect(source).toContain('err.code === "BOOKING_START_IN_PAST"');
    expect(source).toContain('err.code === "BOOKING_START_TOO_SOON"');
    expect(source).toContain("useAlert()");
    expect(source).toContain("showError(message)");
    expect(source).not.toContain('form.setError("startTime"');
    expect(source).toContain("setAvailabilityRefreshToken((token) => token + 1)");
  });

  it("does not render the minimum-advance error inside the schedule or booking form", () => {
    const scheduleSource = readFileSync(
      join(process.cwd(), "src/features/booking/ScheduleBoard.tsx"),
      "utf8",
    );
    const formSource = readFileSync(
      join(process.cwd(), "src/features/booking/booking-form/BookingForm.tsx"),
      "utf8",
    );
    expect(scheduleSource).not.toContain("selectionError");
    expect(formSource).not.toContain("timeNotice=");
  });

  it("does not depend on the unstable eligibility mutation result object", () => {
    const source = readFileSync(
      join(process.cwd(), "src/features/booking/booking-form/BookingLiveChecks.tsx"),
      "utf8",
    );
    expect(source).toContain("mutateAsync: checkEligibility");
    expect(source).toContain("checkEligibilityRef.current");
    expect(source).toContain("eligibilityReqId");
    expect(source).not.toContain("eligibilityMut,");
  });
});
