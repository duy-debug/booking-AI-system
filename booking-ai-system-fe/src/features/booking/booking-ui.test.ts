import { describe, it, expect } from "vitest";
import {
  timeToX,
  durationToWidth,
  nowAbsoluteMinutes,
  formatAbsoluteHour,
  buildTimelineRange,
  parseTimeToMinutes,
  toOvernightEndMinutes,
  floorToStep,
  ceilToStep,
  createDefaultSelection,
  normalizeDraggedSelection,
  calculatePixelsPerMinute,
  FIT_BREAKPOINT,
  MOBILE_PX_PER_MINUTE,
  FULL_DAY_RANGE,
} from "./schedule.utils";
import { shouldUseCompactBookingLayout } from "./BookingLayer";
import { getHourLabelStepMinutes } from "./ScheduleHeader";

describe("FULL_DAY_RANGE (24h timeline)", () => {
  it("rangeStart = 0 (00:00)", () => {
    expect(FULL_DAY_RANGE.start).toBe(0);
  });
  it("rangeEnd = 1440 (00:00 ngày kế tiếp)", () => {
    expect(FULL_DAY_RANGE.end).toBe(1440);
  });
  it("totalMinutes = 1440", () => {
    const total = FULL_DAY_RANGE.end - FULL_DAY_RANGE.start;
    expect(total).toBe(1440);
  });
  it("12:00 nằm đúng 50%", () => {
    const pct = (720 - FULL_DAY_RANGE.start) / (FULL_DAY_RANGE.end - FULL_DAY_RANGE.start);
    expect(pct).toBe(0.5);
  });
  it("18:00 nằm đúng 75%", () => {
    const pct = (1080 - FULL_DAY_RANGE.start) / (FULL_DAY_RANGE.end - FULL_DAY_RANGE.start);
    expect(pct).toBe(0.75);
  });
  it("23:30 nằm đúng vị trí 1410", () => {
    expect(timeToX(1410, FULL_DAY_RANGE, 1)).toBe(1410);
  });
});

describe("booking 23:30-00:30 qua nửa đêm", () => {
  it("toOvernightEndMinutes tính end_time hôm sau", () => {
    const start = parseTimeToMinutes("23:30");
    const end = toOvernightEndMinutes("00:30");
    expect(start).toBe(1410);
    expect(end).toBe(30 + 1440); // 1470
  });
  it("booking block không bị width âm", () => {
    const start = parseTimeToMinutes("23:30");
    const end = toOvernightEndMinutes("00:30");
    expect(end - start).toBeGreaterThan(0);
    expect(end - start).toBe(60); // 60 phút
  });
});

describe("nowAbsoluteMinutes", () => {
  it("trả về null hoặc số trong full-day range", () => {
    const result = nowAbsoluteMinutes(FULL_DAY_RANGE, "2026-07-21", "Asia/Ho_Chi_Minh");
    expect(result === null || typeof result === "number").toBe(true);
    if (result !== null) {
      expect(result).toBeGreaterThanOrEqual(0);
      expect(result).toBeLessThanOrEqual(1440);
    }
  });
});

describe("header có 00:00 và 24:00", () => {
  it("formatAbsoluteHour(0) = 00:00", () => {
    expect(formatAbsoluteHour(0)).toBe("00:00");
  });
  it("formatAbsoluteHour(1440) = 00:00 (wrap, label cuối)", () => {
    expect(formatAbsoluteHour(1440)).toBe("00:00");
  });
});

describe("không còn hard-code 09:00 hoặc 22:00 trong range chính", () => {
  it("FULL_DAY_RANGE không dùng 540 hay 1320", () => {
    expect(FULL_DAY_RANGE.start).not.toBe(540);
    expect(FULL_DAY_RANGE.end).not.toBe(1320);
  });
});

describe("booking left/width (position tính toán)", () => {
  it("timeToX trả về 0 tại start", () => {
    expect(timeToX(0, FULL_DAY_RANGE, 1)).toBe(0);
  });
  it("timeToX 12:00 = 720 với px=1", () => {
    expect(timeToX(720, FULL_DAY_RANGE, 1)).toBe(720);
  });
  it("durationToWidth 90 phút = 360 với px=4", () => {
    expect(durationToWidth(90, 4)).toBe(360);
  });
});

describe("floorToStep / ceilToStep", () => {
  it("floorToStep: 06:47 với step 5 -> 06:45 (405)", () => {
    expect(floorToStep(405 + 2, 5)).toBe(405);
  });
  it("floorToStep: 06:47 với step 10 -> 06:40 (400)", () => {
    expect(floorToStep(405 + 2, 10)).toBe(400);
  });
  it("floorToStep: 06:47 với step 15 -> 06:45 (405)", () => {
    expect(floorToStep(405 + 2, 15)).toBe(405);
  });
  it("floorToStep: 06:47 với step 30 -> 06:30 (390)", () => {
    expect(floorToStep(405 + 2, 30)).toBe(390);
  });
  it("ceilToStep: 06:47 với step 5 -> 06:50 (410)", () => {
    expect(ceilToStep(405 + 2, 5)).toBe(410);
  });
  it("ceilToStep: 06:47 với step 10 -> 06:50 (410)", () => {
    expect(ceilToStep(405 + 2, 10)).toBe(410);
  });
  it("ceilToStep: 06:47 với step 15 -> 07:00 (420)", () => {
    expect(ceilToStep(405 + 2, 15)).toBe(420);
  });
  it("ceilToStep: 06:47 với step 30 -> 07:00 (420)", () => {
    expect(ceilToStep(405 + 2, 30)).toBe(420);
  });
});

describe("createDefaultSelection (click đơn)", () => {
  it("step 5, click 06:47 -> 06:45-06:50 (dài 5 phút)", () => {
    const sel = createDefaultSelection(407, 5, 1440);
    expect(sel.startMinutes).toBe(405); // floor 06:45
    expect(sel.endMinutes).toBe(410);   // +5 = 06:50
    expect(sel.endMinutes - sel.startMinutes).toBe(5);
  });
  it("step 10, click 06:47 -> selection dài 10 phút", () => {
    const sel = createDefaultSelection(407, 10, 1440);
    expect(sel.startMinutes).toBe(400); // floor 06:40
    expect(sel.endMinutes).toBe(410);   // +10 = 06:50
    expect(sel.endMinutes - sel.startMinutes).toBe(10);
  });
  it("step 15, click 06:47 -> selection dài 15 phút", () => {
    const sel = createDefaultSelection(407, 15, 1440);
    expect(sel.startMinutes).toBe(405); // floor 06:45
    expect(sel.endMinutes).toBe(420);   // +15 = 07:00
    expect(sel.endMinutes - sel.startMinutes).toBe(15);
  });
  it("step 30, click 06:47 -> selection dài 30 phút", () => {
    const sel = createDefaultSelection(407, 30, 1440);
    expect(sel.startMinutes).toBe(390); // floor 06:30
    expect(sel.endMinutes).toBe(420);   // +30 = 07:00
    expect(sel.endMinutes - sel.startMinutes).toBe(30);
  });
  it("step 30, click 23:50 -> selection không vượt quá 24:00 (1440)", () => {
    const sel = createDefaultSelection(1430, 30, 1440);
    expect(sel.startMinutes).toBe(1410);
    expect(sel.endMinutes).toBe(1440);
    expect(sel.endMinutes - sel.startMinutes).toBe(30);
  });
});

describe("createDefaultSelection — therapistId", () => {
  it("truyền therapistId và giữ nguyên", () => {
    const sel = createDefaultSelection(400, 15, 1440, "therapist-a");
    expect(sel.therapistId).toBe("therapist-a");
  });
  it("click không truyền therapistId -> undefined", () => {
    const sel = createDefaultSelection(400, 15, 1440);
    expect(sel.therapistId).toBeUndefined();
  });
  it("startMinutes, endMinutes vẫn đúng khi có therapistId", () => {
    const sel = createDefaultSelection(407, 15, 1440, "therapist-b");
    expect(sel.startMinutes).toBe(405);
    expect(sel.endMinutes).toBe(420);
  });
});

function rowSelection(
  selection: { startMinutes: number; endMinutes: number; therapistId?: string } | null,
  therapistId: string,
) {
  return selection?.therapistId === therapistId ? selection : null;
}

describe("rowSelection filter (selection?.therapistId === resource.therapistId)", () => {
  it("trả về selection khi therapistId khớp", () => {
    const selection = { startMinutes: 400, endMinutes: 415, therapistId: "therapist-1" };
    const result = rowSelection(selection, "therapist-1");
    expect(result).toEqual(selection);
  });
  it("trả về null khi therapistId không khớp", () => {
    const selection = { startMinutes: 400, endMinutes: 415, therapistId: "therapist-1" };
    const result = rowSelection(selection, "therapist-2");
    expect(result).toBeNull();
  });
  it("trả về null khi selection là null", () => {
    const result = rowSelection(null, "therapist-1");
    expect(result).toBeNull();
  });
  it("chỉ có tối đa một rowSelection khác null tại một thời điểm", () => {
    const selection = { startMinutes: 400, endMinutes: 415, therapistId: "therapist-1" };
    const rowA = rowSelection(selection, "therapist-1");
    const rowB = rowSelection(selection, "therapist-2");
    expect(rowA).not.toBeNull();
    expect(rowB).toBeNull();
  });
  it("click therapist khác thì selection cũ biến mất", () => {
    const sel1 = { startMinutes: 400, endMinutes: 415, therapistId: "therapist-1" };
    const rowA1 = rowSelection(sel1, "therapist-1");
    expect(rowA1).not.toBeNull();

    const sel2 = { startMinutes: 500, endMinutes: 515, therapistId: "therapist-2" };
    const rowA2 = rowSelection(sel2, "therapist-1");
    const rowB = rowSelection(sel2, "therapist-2");
    expect(rowA2).toBeNull();
    expect(rowB).not.toBeNull();
  });
});

describe("normalizeDraggedSelection", () => {
  it("giữ nguyên therapistId", () => {
    const sel = normalizeDraggedSelection(403, 429, 10, 1440, "therapist-x");
    expect(sel.therapistId).toBe("therapist-x");
  });
  it("không truyền therapistId -> undefined", () => {
    const sel = normalizeDraggedSelection(403, 429, 10, 1440);
    expect(sel.therapistId).toBeUndefined();
  });
  it("drag luôn là bội số của step", () => {
    // drag 06:43 -> 07:09, step 10
    const sel = normalizeDraggedSelection(403, 429, 10, 1440);
    expect(sel.startMinutes).toBe(400); // floor 06:40
    expect(sel.endMinutes).toBe(430);   // ceil 07:10
    expect((sel.endMinutes - sel.startMinutes) % 10).toBe(0);
  });
  it("duration tối thiểu = step khi drag quá ngắn", () => {
    const sel = normalizeDraggedSelection(405, 407, 10, 1440);
    expect(sel.startMinutes).toBe(400);
    expect(sel.endMinutes - sel.startMinutes).toBe(10);
  });
  it("drag đảo start/end vẫn đúng", () => {
    const sel = normalizeDraggedSelection(500, 400, 15, 1440);
    expect(sel.startMinutes).toBe(390);
    expect(sel.endMinutes).toBe(510);
  });
});

describe("calculatePixelsPerMinute", () => {
  it("trả về exact fit: availableWidth / totalMinutes", () => {
    expect(calculatePixelsPerMinute(960, 1440)).toBeCloseTo(0.6667);
  });
  it("viewportWidth=0 trả về 1.0", () => {
    expect(calculatePixelsPerMinute(0, 1440)).toBe(1.0);
  });
  it("1440 phút với viewport 1000px cho kết quả < 1", () => {
    expect(calculatePixelsPerMinute(1000, 1440)).toBeLessThan(1);
  });
});

describe("FIT_BREAKPOINT / MOBILE_PX_PER_MINUTE", () => {
  it("FIT_BREAKPOINT = 1024", () => {
    expect(FIT_BREAKPOINT).toBe(1024);
  });
  it("MOBILE_PX_PER_MINUTE = 0.65", () => {
    expect(MOBILE_PX_PER_MINUTE).toBe(0.65);
  });
});

describe("Business hours timeline (giữ nguyên)", () => {
  it("buildTimelineRange 09:00-22:00 trả về {540, 1320}", () => {
    expect(buildTimelineRange("09:00", "22:00")).toEqual({ start: 540, end: 1320 });
  });
});

describe("booking block responsive content", () => {
  it("hiển thị đầy đủ thông tin khi block rộng từ 48px", () => {
    expect(shouldUseCompactBookingLayout(47)).toBe(true);
    expect(shouldUseCompactBookingLayout(48)).toBe(false);
    expect(shouldUseCompactBookingLayout(79)).toBe(false);
  });
});

describe("timeline hour label density", () => {
  it("giãn nhãn thành hai giờ khi không đủ chỗ và giữ vạch chia theo giờ", () => {
    expect(getHourLabelStepMinutes(0.8)).toBe(120);
    expect(getHourLabelStepMinutes(1)).toBe(60);
  });
});
