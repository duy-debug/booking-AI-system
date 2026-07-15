from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin


class CustomerRestriction(TimestampMixin, Base):
    # NG list — danh sách số điện thoại bị cấm đặt booking
    __tablename__ = "customer_restrictions"

    # Chỉ cho phép 1 active restriction / phone — vẫn lưu lịch sử khi deactivate
    __table_args__ = (
        Index("idx_active_restriction_phone", "phone", unique=True,
              postgresql_where=text("is_active = true")),
    )

    restriction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True  # Số điện thoại bị cấm
    )
    reason: Mapped[str | None] = mapped_column(String(500))  # Lý do cấm
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False  # Còn hiệu lực không
    )

    def __repr__(self) -> str:
        return f"<Restriction {self.phone} active={self.is_active}>"
