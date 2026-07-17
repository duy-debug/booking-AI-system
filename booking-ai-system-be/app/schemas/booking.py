# Schema cho Booking — request/response models

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Course trong booking — gồm course_id và vai trò (main/addon)
class BookingCourseInput(BaseModel):
    course_id: UUID
    course_role: str = Field(..., pattern=r"^(main|addon)$")


# Yêu cầu therapist — none, specific (theo ID) hoặc gender (theo giới tính)
class TherapistRequestInput(BaseModel):
    type: str = Field(..., pattern=r"^(none|specific|gender)$")
    therapist_id: UUID | None = None
    gender: str | None = Field(None, pattern=r"^(male|female)$")


# Thông tin khách hàng khi tạo booking
class CustomerInput(BaseModel):
    phone: str
    name: str | None = None


# Tạo booking mới — request body
class BookingCreate(BaseModel):
    shop_id: UUID
    booking_date: date
    start_time: time
    number_of_people: int = Field(..., ge=1, le=3)
    customer: CustomerInput
    courses: list[BookingCourseInput] = Field(..., min_length=1)
    therapist_request: TherapistRequestInput | None = None
    confirmed_by_customer: bool = True


# Cập nhật booking — các field có thể thay đổi
class BookingUpdate(BaseModel):
    booking_date: date | None = None
    start_time: time | None = None
    courses: list[BookingCourseInput] | None = None
    therapist_request: TherapistRequestInput | None = None


# Huỷ booking — request body
class BookingCancelInput(BaseModel):
    status: str = Field(..., pattern=r"^cancelled$")
    cancel_reason: str | None = None


# Patch booking — tất cả field đều optional
class BookingPatchInput(BaseModel):
    status: str | None = None
    cancel_reason: str | None = None
    booking_date: date | None = None
    start_time: time | None = None
    courses: list[BookingCourseInput] | None = None
    therapist_request: TherapistRequestInput | None = None


# Kiểm tra điều kiện đặt lịch — request body
class BookingEligibilityCheckInput(BaseModel):
    phone: str
    shop_id: UUID


# Response course trong reservation — snapshot giá trị tại thời điểm đặt
class ReservationCourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: UUID
    course_role: str
    course_name_snapshot: str
    duration_snapshot: int
    price_snapshot: Decimal


# Response chi tiết reservation — thông tin therapist, giờ, danh sách course
class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reservation_id: UUID
    person_index: int
    therapist_id: UUID
    start_time: time
    end_time: time
    status: str
    courses: list[ReservationCourseResponse] = []


# Response chi tiết booking (admin) — gồm tất cả field kể cả POS, reservation
class AdminBookingResponse(BaseModel):
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


# Response danh sách booking (admin) — dạng rút gọn, không có reservation
class AdminBookingListItem(BaseModel):
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


# Response chi tiết booking (public) — không có POS field
class PublicBookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    booking_id: UUID
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


# Response danh sách booking (public) — dạng rút gọn
class PublicBookingListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    booking_id: UUID
    shop_id: UUID
    booking_date: date
    start_time: time
    end_time: time
    number_of_people: int
    total_duration_minutes: int
    status: str


# Response kiểm tra điều kiện đặt lịch
class BookingEligibilityCheckResponse(BaseModel):
    check_id: UUID
    phone: str
    eligible: bool
    customer: dict | None = None
    restriction: dict | None = None
