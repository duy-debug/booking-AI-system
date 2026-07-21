import { describe, expect, it } from "vitest";
import type { CourseUiModel } from "@/features/course/course.types";
import {
  courseBaseName,
  courseCategory,
  groupCourseVariants,
} from "./course-matrix";

function course(
  id: string,
  name: string,
  durationMinutes: number,
  courseType: "main" | "addon" = "main",
): CourseUiModel {
  return {
    id,
    shopId: "shop-id",
    posCode: id,
    name,
    durationMinutes,
    price: durationMinutes * 10_000,
    courseType,
    isActive: true,
    createdAt: "2026-07-21T00:00:00Z",
    updatedAt: "2026-07-21T00:00:00Z",
  };
}

describe("course matrix grouping", () => {
  it("groups backend variants by base name and sorts real durations", () => {
    const groups = groupCourseVariants([
      course("body-90", "Massage toàn thân 90 phút", 90),
      course("body-30", "Massage toàn thân 30 phút", 30),
      course("foot-45", "Massage chân 45 phút", 45),
    ]);

    expect(groups).toHaveLength(2);
    expect(groups[0].name).toBe("Massage toàn thân");
    expect(groups[0].variants.map((variant) => variant.durationMinutes)).toEqual([30, 90]);
  });

  it("keeps the real backend course IDs for each duration button", () => {
    const [group] = groupCourseVariants([
      course("real-course-60", "Head Spa 60 min", 60),
      course("real-course-30", "Head Spa 30 min", 30),
    ]);

    expect(group.variants.map((variant) => variant.id)).toEqual([
      "real-course-30",
      "real-course-60",
    ]);
  });

  it("uses supported course type and name only for visual categories", () => {
    expect(courseCategory(course("foot", "Massage chân", 30))).toBe("foot");
    expect(courseCategory(course("head", "Head Spa", 30))).toBe("head");
    expect(courseCategory(course("addon", "Đá nóng", 15, "addon"))).toBe("addon");
  });

  it("does not remove numbers that are part of a course name", () => {
    expect(courseBaseName("Combo 4 tay")).toBe("Combo 4 tay");
  });
});
