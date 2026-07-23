import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  doesSelectionOverlapActiveBooking,
  isMinuteBlockedByBooking,
  splitBookingsByCancellation,
} from "./ResourceRow";
import { createDefaultSelection } from "./schedule.utils";
import type { BookingViewModel } from "./schedule.types";

function booking(status: BookingViewModel["status"]): BookingViewModel {
  return {
    bookingId: `${status}-booking`,
    reservationId: `${status}-reservation`,
    bookingDate: "2026-07-22",
    therapistId: "therapist-1",
    therapistName: "Therapist",
    startMinutes: 600,
    endMinutes: 660,
    status,
    customerName: "Customer",
    customerPhone: "0900000000",
    courseNames: ["Massage"],
    posCode: null,
  };
}

describe("cancelled booking timeline behavior", () => {
  it("keeps cancelled bookings in a visible history layer", () => {
    const layers = splitBookingsByCancellation([
      booking("cancelled"),
      booking("confirmed"),
    ]);
    expect(layers.cancelled).toHaveLength(1);
    expect(layers.active).toHaveLength(1);
  });

  it("allows a click over a cancelled booking to create a selection", () => {
    const cancelled = booking("cancelled");
    expect(isMinuteBlockedByBooking([cancelled], 615)).toBe(false);
    const selection = createDefaultSelection(615, 15, 1440, "therapist-1");
    expect(doesSelectionOverlapActiveBooking([cancelled], selection.startMinutes, selection.endMinutes)).toBe(false);
  });

  it("keeps active bookings blocking click and selection overlap", () => {
    const active = booking("confirmed");
    expect(isMinuteBlockedByBooking([active], 615)).toBe(true);
    expect(doesSelectionOverlapActiveBooking([active], 585, 615)).toBe(true);
  });

  it("blocks the configured break and permits the exact boundary", () => {
    const active = booking("confirmed");
    expect(doesSelectionOverlapActiveBooking([active], 660, 664, 5)).toBe(true);
    expect(doesSelectionOverlapActiveBooking([active], 665, 680, 5)).toBe(false);
    expect(doesSelectionOverlapActiveBooking([active], 540, 596, 5)).toBe(true);
    expect(doesSelectionOverlapActiveBooking([active], 540, 595, 5)).toBe(false);
  });

  it("does not treat a cancelled booking as active overlap for drag ranges", () => {
    expect(doesSelectionOverlapActiveBooking([booking("cancelled")], 590, 670)).toBe(false);
  });

  it("only the cancelled detail button opts back into pointer events", () => {
    const source = readFileSync(
      join(process.cwd(), "src/features/booking/CancelledBookingLayer.tsx"),
      "utf8",
    );
    expect(source).toContain('data-booking-status="cancelled"');
    expect(source).toContain("border-dashed");
    expect(source).toContain("line-through");
    expect(source).toContain("Đã hủy");
    expect(source.match(/pointer-events-auto/g)).toHaveLength(1);
    expect(source).toContain("pointer-events-none absolute overflow-hidden");
  });

  it("renders layers in the required order", () => {
    const source = readFileSync(
      join(process.cwd(), "src/features/booking/ResourceRow.tsx"),
      "utf8",
    );
    const shift = source.indexOf("<ShiftLayer");
    const cancelled = source.indexOf("<CancelledBookingLayer");
    const active = source.indexOf("<BookingLayer");
    const selection = source.indexOf("<SelectionLayer");
    expect(shift).toBeLessThan(cancelled);
    expect(cancelled).toBeLessThan(active);
    expect(active).toBeLessThan(selection);
  });
});
