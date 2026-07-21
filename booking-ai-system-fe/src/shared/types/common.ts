// Enums ánh xạ từ backend (không ép đóng phía frontend ngoại trừ các regex).
// Căn cứ: docs/frontend-analysis.md §4.

export const COURSE_TYPES = ["main", "addon"] as const;
export type CourseType = (typeof COURSE_TYPES)[number];

export const GENDERS = ["male", "female"] as const;
export type Gender = (typeof GENDERS)[number];

export const THERAPIST_REQUEST_TYPES = ["none", "specific", "gender"] as const;
export type TherapistRequestType = (typeof THERAPIST_REQUEST_TYPES)[number];

// Booking status: backend chỉ ép "cancelled" khi huỷ, mặc định "confirmed".
export const BOOKING_STATUSES = ["confirmed", "cancelled"] as const;
export type BookingStatus = (typeof BOOKING_STATUSES)[number];

export const RESERVATION_STATUS = ["assigned"] as const;
export type ReservationStatus = (typeof RESERVATION_STATUS)[number];

export type UUID = string;
export type ISODate = string; // YYYY-MM-DD
export type ISOTime = string; // HH:MM:SS
export type ISODateTime = string; // ISO datetime

// Decimal từ backend serialize thành string trong JSON.
export type DecimalString = string;
