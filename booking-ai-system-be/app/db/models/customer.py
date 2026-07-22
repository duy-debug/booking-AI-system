from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False  # SĐT — định danh khách hàng
    )
    name: Mapped[str | None] = mapped_column(String(255))  # Tên khách hàng
    pos_customer_code: Mapped[str | None] = mapped_column(String(50))  # Mã khách bên POS
    is_member: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False  # Có phải thành viên không
    )
    member_rank: Mapped[str | None] = mapped_column(String(50))  # Hạng thành viên (gold, silver...)
    visit_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False  # Số lần đã ghé
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)  # Lần cuối đồng bộ từ POS
    )

    bookings = relationship("Booking", back_populates="customer")

    # Tạo chuỗi đại diện chứa số điện thoại và tên khách hàng khi kiểm tra dữ liệu ORM.
    def __repr__(self) -> str:
        return f"<Customer {self.phone} - {self.name}>"
