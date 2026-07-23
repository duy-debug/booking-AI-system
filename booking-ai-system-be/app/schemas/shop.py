# Schema cho Shop — request/response models

from __future__ import annotations

from datetime import datetime
from typing import Literal
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
    therapist_break_minutes: Literal[0, 5, 10, 15] = 0


# Cập nhật shop — tất cả field đều optional (PATCH)
class ShopUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    therapist_break_minutes: Literal[0, 5, 10, 15] | None = None


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
    therapist_break_minutes: Literal[0, 5, 10, 15]
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


# Các đường dẫn liên quan giúp client điều hướng từ shop sang course và slot khả dụng.
class PublicShopLinks(BaseModel):
    self: str
    courses: str
    available_slots: str


# Shop trong danh sách public kèm HATEOAS links.
class PublicShopListResponse(PublicShopResponse):
    links: PublicShopLinks


# Shop dạng rút gọn — dùng trong nesting
class ShopBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shop_id: UUID
    name: str
