# Schema cho Customer — khách hàng

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# Response chi tiết khách hàng
class CustomerResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    customer_id: UUID
    phone: str
    name: str | None = None
    is_member: bool
    member_rank: str | None = None
    visit_count: int
    last_synced_at: datetime | None = None


# Customer dạng rút gọn — dùng trong nesting
class CustomerBrief(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    customer_id: UUID
    phone: str
    name: str | None = None
