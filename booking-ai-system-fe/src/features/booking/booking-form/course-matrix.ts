import type { CourseUiModel } from "@/features/course/course.types";

export type CourseCategory = "primary" | "foot" | "head" | "addon";

export interface CourseVariantGroup {
  key: string;
  name: string;
  category: CourseCategory;
  variants: CourseUiModel[];
}

export const courseCategoryStyles: Record<
  CourseCategory,
  { label: string; idle: string; selected: string }
> = {
  primary: {
    label: "border-amber-300 bg-amber-50 text-amber-950",
    idle: "border-amber-300 bg-amber-100 text-amber-950 hover:bg-amber-200",
    selected: "border-amber-700 bg-amber-400 text-amber-950 ring-2 ring-amber-700",
  },
  foot: {
    label: "border-rose-300 bg-rose-50 text-rose-950",
    idle: "border-rose-300 bg-rose-100 text-rose-950 hover:bg-rose-200",
    selected: "border-rose-700 bg-rose-500 text-white ring-2 ring-rose-700",
  },
  head: {
    label: "border-cyan-300 bg-cyan-50 text-cyan-950",
    idle: "border-cyan-300 bg-cyan-100 text-cyan-950 hover:bg-cyan-200",
    selected: "border-cyan-700 bg-cyan-500 text-white ring-2 ring-cyan-700",
  },
  addon: {
    label: "border-blue-300 bg-blue-50 text-blue-950",
    idle: "border-blue-300 bg-blue-100 text-blue-950 hover:bg-blue-200",
    selected: "border-blue-700 bg-blue-600 text-white ring-2 ring-blue-700",
  },
};

export function courseBaseName(name: string): string {
  const withoutDuration = name.replace(
    /\s*[-–—(/]?\s*\d+\s*(?:phút|phut|minutes?|mins?|min|p)\s*\)?\s*$/i,
    "",
  );
  return withoutDuration.trim() || name.trim();
}

export function courseCategory(course: CourseUiModel): CourseCategory {
  if (course.courseType === "addon") return "addon";
  const name = course.name.toLocaleLowerCase("vi");
  if (/chân|chan|foot|leg/.test(name)) return "foot";
  if (/đầu|dau|head|scalp/.test(name)) return "head";
  return "primary";
}

export function groupCourseVariants(courses: CourseUiModel[]): CourseVariantGroup[] {
  const groups = new Map<string, CourseVariantGroup>();

  for (const course of courses) {
    const name = courseBaseName(course.name);
    const key = `${course.courseType}:${name.toLocaleLowerCase("vi")}`;
    const current = groups.get(key);
    if (current) {
      current.variants.push(course);
    } else {
      groups.set(key, {
        key,
        name,
        category: courseCategory(course),
        variants: [course],
      });
    }
  }

  return Array.from(groups.values()).map((group) => ({
    ...group,
    variants: [...group.variants].sort(
      (a, b) => a.durationMinutes - b.durationMinutes || a.name.localeCompare(b.name),
    ),
  }));
}
