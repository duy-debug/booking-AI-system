import { SHOP_TIMEZONE } from "@/shared/config/shop";

// Backend lưu start_time/end_time/work_date là giá trị NAIVE (không có múi giờ).
// Shop mặc định ở Asia/Ho_Chi_Minh. Mọi hiển thị & parse phải dựa vào múi giờ này.
// Căn cứ: docs/frontend-analysis.md §6.7, §9.

const timeZone = SHOP_TIMEZONE;

// Format giờ HH:MM:SS (naive) thành chuỗi hiển thị theo múi giờ shop.
export function formatShopTime(time: string, opts?: Intl.DateTimeFormatOptions): string {
  // Gắn vào một ngày tham chiếu để có thể format theo tz.
  const [h, m, s] = time.split(":").map(Number);
  const ref = new Date();
  ref.setFullYear(2000, 0, 1);
  ref.setHours(h, m ?? 0, s ?? 0, 0);
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    ...opts,
  }).format(ref);
}

// Format ngày YYYY-MM-DD theo múi giờ shop.
export function formatShopDate(date: string, opts?: Intl.DateTimeFormatOptions): string {
  const [y, m, d] = date.split("-").map(Number);
  const ref = new Date();
  ref.setFullYear(y, (m ?? 1) - 1, d ?? 1);
  ref.setHours(12, 0, 0, 0);
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    ...opts,
  }).format(ref);
}

// Backend KHÔNG lưu ngày kết thúc khi booking qua nửa đêm (chỉ lưu giờ).
// Hàm này tính endDate: nếu endTime < startTime => cộng 1 ngày.
// Căn cứ: app/services/booking_service.py:258-262, docs §6.8.
export function resolveEndDate(
  startDate: string,
  startTime: string,
  endTime: string,
): string {
  if (endTime < startTime) {
    const [y, m, d] = startDate.split("-").map(Number);
    const dt = new Date();
    dt.setFullYear(y, (m ?? 1) - 1, (d ?? 1) + 1);
    const yyyy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    const dd = String(dt.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }
  return startDate;
}

// Parse một ISO datetime (có thể là TIMESTAMPTZ UTC) sang hiển thị theo múi giờ shop.
export function formatShopDateTime(iso: string | null, opts?: Intl.DateTimeFormatOptions): string {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    ...opts,
  }).format(dt);
}

// Chuẩn hóa Decimal string -> number (backend trả price dạng string).
// Căn cứ: docs/frontend-analysis.md §6.2.
export function parseDecimal(value: string | number | null | undefined): number {
  if (value == null) return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

// Format tiền VND.
export function formatVND(value: string | number | null | undefined): string {
  const n = parseDecimal(value);
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(n);
}

// Lấy ngày hôm nay theo múi giờ shop dưới dạng YYYY-MM-DD.
export function todayShopDate(): string {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  return parts; // en-CA trả YYYY-MM-DD
}
