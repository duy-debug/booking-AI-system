# Schema cho Therapist — nhân viên massage

from __future__ import annotations

from datetime import datetime
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
