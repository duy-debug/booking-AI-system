import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/shared/hooks/api", () => ({
  apiClient: { get: vi.fn() },
  useApiMutation: vi.fn(),
}));

import { apiClient } from "@/shared/hooks/api";
import {
  checkAvailableSlots,
  checkAvailableTherapists,
  type AvailableSlot,
  type AvailableTherapist,
} from "./booking-form.queries";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("booking availability queries", () => {
  it("returns the slot array already unwrapped by apiClient", async () => {
    const slots: AvailableSlot[] = [
      {
        start_time: "10:00:00",
        end_time: "11:00:00",
        duration_minutes: 60,
        available: true,
      },
    ];
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(slots);

    await expect(
      checkAvailableSlots({
        shopId: "shop-id",
        bookingDate: "2026-07-21",
        startTime: "10:01",
        numberOfPeople: 1,
        mainCourseId: "course-id",
      }),
    ).resolves.toEqual(slots);

    expect(get).toHaveBeenCalledWith("/api/shops/shop-id/available-slots", {
      query: {
        booking_date: "2026-07-21",
        start_time: "10:01",
        number_of_people: "1",
        main_course_id: "course-id",
      },
      anonymous: true,
    });
  });

  it("returns the therapist array already unwrapped by apiClient", async () => {
    const therapists: AvailableTherapist[] = [
      {
        therapist_id: "therapist-id",
        shop_id: "shop-id",
        name: "Therapist",
        gender: "female",
        available: true,
      },
    ];
    vi.spyOn(apiClient, "get").mockResolvedValue(therapists);

    await expect(
      checkAvailableTherapists({
        shopId: "shop-id",
        bookingDate: "2026-07-21",
        startTime: "10:00",
        endTime: "11:00",
      }),
    ).resolves.toEqual(therapists);
  });

  it("does not send therapist_id for a group availability request", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue([]);

    await checkAvailableSlots({
      shopId: "shop-id",
      bookingDate: "2026-07-21",
      numberOfPeople: 2,
      mainCourseId: "course-id",
      therapistRequestType: "specific",
      therapistId: "therapist-a",
    });

    expect(get).toHaveBeenCalledWith("/api/shops/shop-id/available-slots", {
      query: {
        booking_date: "2026-07-21",
        number_of_people: "2",
        main_course_id: "course-id",
        therapist_request_type: "none",
      },
      anonymous: true,
    });
  });
});
