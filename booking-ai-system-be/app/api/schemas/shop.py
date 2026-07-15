# Schema cho Shop — cửa hàng massage

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ShopCreate(BaseModel):
    """Tạo shop mới — request body"""

    shop_code: str
    pos_shop_code: str
    name: str
    address: str | None = None
    phone: str | None = None
    is_active: bool = True


class ShopUpdate(BaseModel):
    """Cập nhật shop — tất cả field đều optional (PATCH)"""

    name: str | None = None
    address: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class ShopResponse(BaseModel):
    """Response chi tiết shop — dùng cho GET /admin/shops/{id}, POST, PATCH"""

    model_config = ConfigDict(from_attributes=True)

    shop_id: UUID
    shop_code: str
    pos_shop_code: str
    name: str
    address: str | None = None
    phone: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ShopBrief(BaseModel):
    """Shop dạng rút gọn — dùng trong nesting (Booking, Course, ...)"""

    model_config = ConfigDict(from_attributes=True)

    shop_id: UUID
    name: str
