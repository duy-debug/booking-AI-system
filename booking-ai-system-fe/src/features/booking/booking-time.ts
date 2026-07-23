export const DEFAULT_MINIMUM_BOOKING_ADVANCE_MINUTES = 15;

export type BookingStartErrorCode =
  | "BOOKING_START_IN_PAST"
  | "BOOKING_START_TOO_SOON";

export interface BookingStartValidation {
  valid: boolean;
  code?: BookingStartErrorCode;
  message?: string;
  earliestSelectableMinutes?: number;
}

interface ZonedParts {
  date: string;
  seconds: number;
}

// Tách ngày giờ theo timezone của shop thay vì timezone máy người dùng để so sánh chính xác.
function zonedParts(value: Date, timeZone: string): ZonedParts {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  // Đọc một date-time part đã format và chuyển sang số để xây cấu trúc ZonedParts.
  const read = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "00";
  const date = `${read("year")}-${read("month")}-${read("day")}`;
  return {
    date,
    seconds:
      Number(read("hour")) * 3600 +
      Number(read("minute")) * 60 +
      Number(read("second")),
  };
}

// Tính phút bắt đầu sớm nhất sau khi cộng thời gian đặt trước, chính xác tới từng phút.
export function earliestSelectableForDate({
  bookingDate,
  timeZone,
  now = new Date(),
  advanceMinutes = DEFAULT_MINIMUM_BOOKING_ADVANCE_MINUTES,
}: {
  bookingDate: string;
  timeZone: string;
  now?: Date;
  advanceMinutes?: number;
}): number | null {
  const current = zonedParts(now, timeZone);
  if (bookingDate < current.date) return Number.POSITIVE_INFINITY;

  const earliest = zonedParts(new Date(now.getTime() + advanceMinutes * 60_000), timeZone);
  if (bookingDate < earliest.date) return Number.POSITIVE_INFINITY;
  if (bookingDate > earliest.date) return null;
  return Math.ceil(earliest.seconds / 60);
}

// Kiểm tra selection có nằm trong quá khứ hoặc sát giờ hơn giới hạn đặt trước hay không.
export function validateBookingStart({
  bookingDate,
  startMinutes,
  timeZone,
  now = new Date(),
  advanceMinutes = DEFAULT_MINIMUM_BOOKING_ADVANCE_MINUTES,
}: {
  bookingDate: string;
  startMinutes: number;
  timeZone: string;
  now?: Date;
  advanceMinutes?: number;
}): BookingStartValidation {
  const current = zonedParts(now, timeZone);
  const startSeconds = startMinutes * 60;
  if (bookingDate < current.date || (bookingDate === current.date && startSeconds < current.seconds)) {
    return {
      valid: false,
      code: "BOOKING_START_IN_PAST",
      message: "Không thể tạo booking trong quá khứ.",
    };
  }

  const earliest = zonedParts(new Date(now.getTime() + advanceMinutes * 60_000), timeZone);
  if (bookingDate < earliest.date || (bookingDate === earliest.date && startSeconds < earliest.seconds)) {
    return {
      valid: false,
      code: "BOOKING_START_TOO_SOON",
      message: `Booking phải bắt đầu sau ít nhất ${advanceMinutes} phút.`,
    };
  }
  return { valid: true };
}
