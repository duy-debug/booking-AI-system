# Schema cho CustomerRestriction — NG list (số điện thoại bị cấm)

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# Tạo restriction mới — request body
class RestrictionCreate(BaseModel):

    phone: str
    reason: str | None = None
    is_active: bool = True


# Cập nhật restriction — tất cả field đều optional (PATCH)
class RestrictionUpdate(BaseModel):

    reason: str | None = None
    is_active: bool | None = None


# Response chi tiết restriction
class RestrictionResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    restriction_id: UUID
    phone: str
    reason: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
