# Schema cho Customer — khách hàng

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CustomerResponse(BaseModel):
    """Response chi tiết khách hàng"""

    model_config = ConfigDict(from_attributes=True)

    customer_id: UUID
    phone: str
    name: str | None = None
    is_member: bool
    member_rank: str | None = None
    visit_count: int
    last_synced_at: datetime | None = None


class CustomerBrief(BaseModel):
    """Customer dạng rút gọn — dùng trong nesting"""

    model_config = ConfigDict(from_attributes=True)

    customer_id: UUID
    phone: str
    name: str | None = None
