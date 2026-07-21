// Tách riêng toàn bộ logic thời gian <-> vị trí pixel và xử lý qua nửa đêm.
// Không tính timezone rải rác trong component (nguyên tắc 6).
// Backend lưu time là giá trị NAIVE (không múi giờ) — xem docs/frontend-analysis.md §6.7, §9.

export const MINUTES_PER_DAY = 1440;

export interface TimeRange {
  // Phút tuyệt đối của đầu timeline (vd 09:00 = 540)
  start: number;
  // Phút tuyệt đối của cuối timeline (vd 05:00 hôm sau = 300 + 1440 = 1740)
  end: number;
}

// "HH:MM" hoặc "HH:MM:SS" -> số phút từ 00:00 (0..1439)
export function parseTimeToMinutes(time: string): number {
  const [h, m] = time.split(":").map(Number);
  return h * 60 + m;
}

// Chuyển giờ thành phút tuyệt đối trên timeline, xử lý qua nửa đêm.
// Nếu giờ < start (vd 01:00 khi start=09:00) => coi là sang ngày hôm sau (+1440).
export function toAbsoluteMinutes(time: string, timelineStart: number): number {
  let mins = parseTimeToMinutes(time);
  if (mins < timelineStart && timelineStart >= 0) {
    // chỉ cộng 1 ngày khi timeline đi qua nửa đêm (end > start + 1440 là không, nhưng end > start)
    mins += MINUTES_PER_DAY;
  }
  return mins;
}

// Phút tuyệt đối trên timeline -> "HH:MM" (naive, giờ đồng hồ).
// Dùng để prefill giờ bắt đầu khi user click một ô trống / booking.
export function absoluteMinutesToHHMM(absMinutes: number): string {
  const m = ((absMinutes % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  const hh = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(m % 60).padStart(2, "0");
  return `${hh}:${mm}`;
}

// Tổng số phút của timeline (có thể > 1440 nếu qua nửa đêm)
export function timelineDuration(range: TimeRange): number {
  return range.end - range.start;
}

// Vị trí X (px) của một giờ tuyệt đối so với đầu timeline
export function timeToX(
  absoluteMinutes: number,
  range: TimeRange,
  pxPerMinute: number,
): number {
  return (absoluteMinutes - range.start) * pxPerMinute;
}

// Ngược lại: từ X (px) sang phút tuyệt đối
export function xToMinutes(x: number, range: TimeRange, pxPerMinute: number): number {
  return range.start + x / pxPerMinute;
}

// Độ rộng (px) của một khoảng thời lượng
export function durationToWidth(durationMinutes: number, pxPerMinute: number): number {
  return durationMinutes * pxPerMinute;
}

// Format nhãn giờ. Khi qua nửa đêm, 01:00 -> "25:00" (absoluteMinutes >= 1440).
// Trả về "HH:MM".
export function formatAbsoluteHour(absoluteMinutes: number, opts?: { padDay?: boolean }): string {
  const m = ((absoluteMinutes % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  // Nếu absolute >= 1440 và padDay -> hiển thị giờ + 24
  if (opts?.padDay && absoluteMinutes >= MINUTES_PER_DAY) {
    const hDay = h + 24;
    return `${String(hDay).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
  }
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

// Sinh danh sách nhãn giờ theo step (phút) cho header
export function buildHourTicks(
  range: TimeRange,
  stepMinutes: number,
  opts?: { padDay?: boolean },
): Array<{ absoluteMinutes: number; label: string; x: number; pxPerMinute: number }> {
  const pxPerMinute = stepMinutes; // placeholder; thực tế pxPerMinute tính riêng
  const ticks: Array<{ absoluteMinutes: number; label: string; x: number; pxPerMinute: number }> = [];
  for (let t = range.start; t <= range.end; t += stepMinutes) {
    ticks.push({
      absoluteMinutes: t,
      label: formatAbsoluteHour(t, opts),
      x: (t - range.start) * 1, // caller sẽ nhân pxPerMinute
      pxPerMinute,
    });
  }
  return ticks;
}

// Snap một phút tuyệt đối vào bước chia (vd 15 phút)
export function snapMinutes(absoluteMinutes: number, stepMinutes: number): number {
  return Math.round(absoluteMinutes / stepMinutes) * stepMinutes;
}

// Tính khoảng thời gian hiện tại (phút tuyệt đối) từ Date thực tế theo múi giờ shop.
// Dùng cho CurrentTimeLine. Cần shop timezone.
export function nowAbsoluteMinutes(
  range: TimeRange,
  dateStr: string,
  timezone: string,
): number | null {
  const now = new Date();
  const timeStr = new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(now);
  const mins = parseTimeToMinutes(timeStr);
  // Nếu giờ hiện tại < start và timeline qua nửa đêm -> coi là ngày hôm sau
  if (mins < range.start && range.end > range.start + MINUTES_PER_DAY) {
    return mins + MINUTES_PER_DAY;
  }
  if (mins < range.start || mins > range.end) return null; // ngoài khung
  return mins;
}

// Tính khoảng timeline từ business hours, hỗ trợ qua nửa đêm.
// Ví dụ open=09:00, close=05:00 -> start=540, end=300+1440=1740.
export function buildTimelineRange(
  open: string,
  close: string,
): TimeRange {
  const start = parseTimeToMinutes(open);
  let end = parseTimeToMinutes(close);
  if (end <= start) end += MINUTES_PER_DAY; // qua nửa đêm
  return { start, end };
}

