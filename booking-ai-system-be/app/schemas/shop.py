# Schema cho Shop — request/response models

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# Tạo shop mới — request body
class ShopCreate(BaseModel):
    shop_code: str
    pos_shop_code: str
    name: str
    address: str | None = None
    phone: str | None = None
    is_active: bool = True


# Cập nhật shop — tất cả field đều optional (PATCH)
class ShopUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    is_active: bool | None = None


# Response chi tiết shop (admin) — gồm tất cả field
class AdminShopResponse(BaseModel):
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


# Response công khai shop — chỉ field cơ bản, không có is_active/created_at/updated_at
class PublicShopResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shop_id: UUID
    shop_code: str
    name: str
    address: str | None = None
    phone: str | None = None


# Shop dạng rút gọn — dùng trong nesting
class ShopBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shop_id: UUID
    name: str
