# Schema cho TherapistShift — ca làm việc của therapist

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ShiftCreate(BaseModel):
    """Tạo ca làm việc mới — request body"""

    shop_id: UUID
    therapist_id: UUID
    work_date: date
    start_time: time
    end_time: time
    is_active: bool = True


class ShiftUpdate(BaseModel):
    """Cập nhật ca làm việc — tất cả field đều optional (PATCH)"""

    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None


class ShiftResponse(BaseModel):
    """Response chi tiết ca làm việc"""

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
