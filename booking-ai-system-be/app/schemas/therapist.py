# Schema cho Therapist — nhân viên massage

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Tạo therapist mới — request body
class TherapistCreate(BaseModel):

    pos_therapist_code: str
    name: str
    gender: str = Field(..., pattern=r"^(male|female)$")
    is_active: bool = True


# Cập nhật therapist — tất cả field đều optional (PATCH)
class TherapistUpdate(BaseModel):

    name: str | None = None
    gender: str | None = Field(None, pattern=r"^(male|female)$")
    is_active: bool | None = None


# Response chi tiết therapist
class TherapistResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    therapist_id: UUID
    shop_id: UUID
    pos_therapist_code: str
    name: str
    gender: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Therapist dạng rút gọn — dùng trong nesting
class TherapistBrief(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    therapist_id: UUID
    name: str


class PublicTherapistResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    therapist_id: UUID
    shop_id: UUID
    name: str
    gender: str
    is_active: bool


# Ca làm việc rút gọn trong lịch cá nhân của therapist.
class TherapistScheduleShiftResponse(BaseModel):
    start_time: time | None
    end_time: time | None


# Reservation được hiển thị trong lịch cá nhân của therapist.
class TherapistScheduleReservationResponse(BaseModel):
    reservation_id: UUID
    booking_id: UUID
    start_time: time
    end_time: time
    course_names: list[str]
    booking_status: str | None


# Lịch làm việc và các reservation của một therapist trong ngày.
class TherapistScheduleResponse(BaseModel):
    therapist_id: UUID
    date: date
    shift: TherapistScheduleShiftResponse | None
    reservations: list[TherapistScheduleReservationResponse]
