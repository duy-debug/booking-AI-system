from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Shop(TimestampMixin, Base):
    __tablename__ = "shops"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False  # Mã cửa hàng nội bộ
    )
    pos_shop_code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False  # Mã cửa hàng bên POS
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # Tên cửa hàng
    address: Mapped[str | None] = mapped_column(String(500))  # Địa chỉ
    phone: Mapped[str | None] = mapped_column(String(20))  # Số điện thoại liên hệ
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False  # Trạng thái hoạt động
    )

    courses = relationship("Course", back_populates="shop")
    therapists = relationship("Therapist", back_populates="shop")
    therapist_shifts = relationship("TherapistShift", back_populates="shop")
    bookings = relationship("Booking", back_populates="shop")

    # Tạo chuỗi đại diện gồm mã và tên shop để hỗ trợ log và debug ORM.
    def __repr__(self) -> str:
        return f"<Shop {self.shop_code} - {self.name}>"
