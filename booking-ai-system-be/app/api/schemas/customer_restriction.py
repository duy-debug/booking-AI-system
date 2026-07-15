# Schema cho CustomerRestriction — NG list (số điện thoại bị cấm)

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RestrictionCreate(BaseModel):
    """Tạo restriction mới — request body"""

    phone: str
    reason: str | None = None
    is_active: bool = True


class RestrictionUpdate(BaseModel):
    """Cập nhật restriction — tất cả field đều optional (PATCH)"""

    reason: str | None = None
    is_active: bool | None = None


class RestrictionResponse(BaseModel):
    """Response chi tiết restriction"""

    model_config = ConfigDict(from_attributes=True)

    restriction_id: UUID
    phone: str
    reason: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
