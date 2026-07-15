# Schema cho Booking — đặt lịch massage (bao gồm Reservation + ReservationCourse lồng bên trong)

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ────────────── Input (request) schemas ──────────────


class BookingCourseInput(BaseModel):
    """Course được chọn trong booking — request body"""

    course_id: UUID
    course_role: str = Field(..., pattern=r"^(main|addon)$")


class TherapistRequestInput(BaseModel):
    """Yêu cầu therapist — request body"""

    type: str = Field(..., pattern=r"^(none|specific|gender)$")
    therapist_id: UUID | None = None
    gender: str | None = Field(None, pattern=r"^(male|female)$")


class CustomerInput(BaseModel):
    """Thông tin khách hàng gửi lên — request body"""

    phone: str
    name: str | None = None


class BookingCreate(BaseModel):
    """Tạo booking mới — request body (POST /api/bookings)"""

    shop_id: UUID
    booking_date: date
    start_time: time
    number_of_people: int = Field(..., ge=1, le=3)
    customer: CustomerInput
    courses: list[BookingCourseInput] = Field(..., min_length=1)
    therapist_request: TherapistRequestInput | None = None
    confirmed_by_customer: bool = True


class BookingUpdate(BaseModel):
    """Cập nhật booking — request body (PATCH /api/bookings/{id})"""

    booking_date: date | None = None
    start_time: time | None = None
    courses: list[BookingCourseInput] | None = None
    therapist_request: TherapistRequestInput | None = None


class BookingCancelInput(BaseModel):
    """Hủy booking — request body"""

    status: str = Field(..., pattern=r"^cancelled$")
    cancel_reason: str | None = None


class BookingPatchInput(BaseModel):
    """Cập nhật hoặc hủy booking — dùng chung cho PATCH /api/bookings/{id}
    - Nếu gửi status=cancelled → hủy booking
    - Nếu gửi các field khác → cập nhật booking"""

    status: str | None = None
    cancel_reason: str | None = None
    booking_date: date | None = None
    start_time: time | None = None
    courses: list[BookingCourseInput] | None = None
    therapist_request: TherapistRequestInput | None = None


class BookingEligibilityCheckInput(BaseModel):
    """Kiểm tra eligibility — request body (POST /api/booking-eligibility-checks)"""

    phone: str
    shop_id: UUID


# ────────────── Output (response) schemas ──────────────


class ReservationCourseResponse(BaseModel):
    """Course snapshot trong reservation — response"""

    model_config = ConfigDict(from_attributes=True)

    course_id: UUID
    course_role: str
    course_name_snapshot: str
    duration_snapshot: int
    price_snapshot: Decimal


class ReservationResponse(BaseModel):
    """Reservation (một người trong booking) — response"""

    model_config = ConfigDict(from_attributes=True)

    reservation_id: UUID
    person_index: int
    therapist_id: UUID
    start_time: time
    end_time: time
    status: str
    courses: list[ReservationCourseResponse] = []


class BookingResponse(BaseModel):
    """Response chi tiết booking — dùng cho GET /api/bookings/{id}"""

    model_config = ConfigDict(from_attributes=True)

    booking_id: UUID
    pos_booking_code: str | None = None
    pos_sync_status: str = "pending"
    shop_id: UUID
    customer_id: UUID
    booking_date: date
    start_time: time
    end_time: time
    number_of_people: int
    total_duration_minutes: int
    status: str
    therapist_request_type: str
    requested_therapist_id: UUID | None = None
    requested_gender: str | None = None
    cancel_reason: str | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    reservations: list[ReservationResponse] = []


class BookingListItem(BaseModel):
    """Booking dạng danh sách — response cho GET /api/bookings"""

    model_config = ConfigDict(from_attributes=True)

    booking_id: UUID
    pos_booking_code: str | None = None
    pos_sync_status: str = "pending"
    shop_id: UUID
    booking_date: date
    start_time: time
    end_time: time
    number_of_people: int
    total_duration_minutes: int
    status: str


class BookingEligibilityCheckResponse(BaseModel):
    """Kết quả kiểm tra eligibility"""

    check_id: UUID
    phone: str
    eligible: bool
    customer: dict | None = None  # CustomerBrief-like dict
    restriction: dict | None = None  # RestrictionResponse-like dict
