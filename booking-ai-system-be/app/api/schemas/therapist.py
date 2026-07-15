# Schema cho Therapist — nhân viên massage

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TherapistCreate(BaseModel):
    """Tạo therapist mới — request body"""

    pos_therapist_code: str
    name: str
    gender: str = Field(..., pattern=r"^(male|female)$")
    is_active: bool = True


class TherapistUpdate(BaseModel):
    """Cập nhật therapist — tất cả field đều optional (PATCH)"""

    name: str | None = None
    gender: str | None = Field(None, pattern=r"^(male|female)$")
    is_active: bool | None = None


class TherapistResponse(BaseModel):
    """Response chi tiết therapist"""

    model_config = ConfigDict(from_attributes=True)

    therapist_id: UUID
    shop_id: UUID
    pos_therapist_code: str
    name: str
    gender: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TherapistBrief(BaseModel):
    """Therapist dạng rút gọn — dùng trong nesting"""

    model_config = ConfigDict(from_attributes=True)

    therapist_id: UUID
    name: str
