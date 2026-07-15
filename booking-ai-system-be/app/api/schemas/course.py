# Schema cho Course — dịch vụ massage (main / addon)

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


VALID_COURSE_TYPES = {"main", "addon"}


class CourseCreate(BaseModel):
    """Tạo course mới — request body"""

    pos_course_code: str
    name: str
    duration_minutes: int = Field(..., ge=15, multiple_of=15)
    price: Decimal = Field(..., ge=0, decimal_places=2)
    course_type: str = Field(..., pattern=r"^(main|addon)$")
    is_active: bool = True


class CourseUpdate(BaseModel):
    """Cập nhật course — tất cả field đều optional (PATCH)"""

    name: str | None = None
    duration_minutes: int | None = Field(None, ge=15, multiple_of=15)
    price: Decimal | None = Field(None, ge=0, decimal_places=2)
    course_type: str | None = Field(None, pattern=r"^(main|addon)$")
    is_active: bool | None = None


class CourseResponse(BaseModel):
    """Response chi tiết course"""

    model_config = ConfigDict(from_attributes=True)

    course_id: UUID
    shop_id: UUID
    pos_course_code: str
    name: str
    duration_minutes: int
    price: Decimal
    course_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
