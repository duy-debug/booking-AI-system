# Schema cho TherapistShift — ca làm việc của therapist

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# Tạo ca làm việc mới — request body
class ShiftCreate(BaseModel):

    shop_id: UUID
    therapist_id: UUID
    work_date: date
    start_time: time
    end_time: time
    is_active: bool = True


# Cập nhật ca làm việc — tất cả field đều optional (PATCH)
class ShiftUpdate(BaseModel):

    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None


# Response chi tiết ca làm việc
class ShiftResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    shift_id: UUID
    shop_id: UUID
    therapist_id: UUID
    work_date: date
    start_time: time
    end_time: time
    is_active: bool
    created_at: datetime
    updated_at: datetime
