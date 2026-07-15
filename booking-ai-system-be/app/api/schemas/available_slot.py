# Schema cho Available Slots và Available Therapists
# Slot là computed resource — không có bảng riêng trong DB

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, Field


class AvailableSlotQuery(BaseModel):
    """Query params cho GET /api/shops/{id}/available-slots"""

    booking_date: date
    number_of_people: int = Field(..., ge=1, le=3)
    main_course_id: UUID
    addon_course_ids: str | None = None  # comma-separated UUIDs
    therapist_request_type: str | None = Field(None, pattern=r"^(none|specific|gender)$")
    therapist_id: UUID | None = None
    therapist_gender: str | None = Field(None, pattern=r"^(male|female)$")


class AvailableSlotResponse(BaseModel):
    """Một slot khả dụng"""

    start_time: time
    end_time: time
    duration_minutes: int
    available: bool


class AvailableSlotMeta(BaseModel):
    """Meta data cho available-slots response"""

    booking_date: date
    shop_id: UUID
    number_of_people: int


class AvailableTherapistQuery(BaseModel):
    """Query params cho GET /api/shops/{id}/available-therapists"""

    booking_date: date
    start_time: time
    end_time: time
    gender: str | None = Field(None, pattern=r"^(male|female|any)$")


class AvailableTherapistResponse(BaseModel):
    """Một therapist khả dụng"""

    therapist_id: UUID
    shop_id: UUID
    name: str
    gender: str
    available: bool
