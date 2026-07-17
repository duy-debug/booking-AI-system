# Schema cho Available Slots và Available Therapists
# Slot là computed resource — không có bảng riêng trong DB

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, Field


# Query params cho GET /api/shops/{id}/available-slots
class AvailableSlotQuery(BaseModel):

    booking_date: date
    number_of_people: int = Field(..., ge=1, le=3)
    main_course_id: UUID
    addon_course_ids: str | None = None  # UUIDs cách nhau bằng dấu phẩy
    therapist_request_type: str | None = Field(None, pattern=r"^(none|specific|gender)$")
    therapist_id: UUID | None = None
    therapist_gender: str | None = Field(None, pattern=r"^(male|female)$")


# Một slot khả dụng
class AvailableSlotResponse(BaseModel):

    start_time: time
    end_time: time
    duration_minutes: int
    available: bool


# Meta data cho available-slots response
class AvailableSlotMeta(BaseModel):

    booking_date: date
    shop_id: UUID
    number_of_people: int


# Query params cho GET /api/shops/{id}/available-therapists
class AvailableTherapistQuery(BaseModel):

    booking_date: date
    start_time: time
    end_time: time
    gender: str | None = Field(None, pattern=r"^(male|female|any)$")


# Một therapist khả dụng
class AvailableTherapistResponse(BaseModel):

    therapist_id: UUID
    shop_id: UUID
    name: str
    gender: str
    available: bool
