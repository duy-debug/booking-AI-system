from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Therapist(TimestampMixin, Base):
    __tablename__ = "therapists"

    # pos_therapist_code là duy nhất trong phạm vi một shop
    __table_args__ = (
        Index("uq_therapist_per_shop", "shop_id", "pos_therapist_code", unique=True),
    )

    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.shop_id"), nullable=False, index=True
    )
    pos_therapist_code: Mapped[str] = mapped_column(String(50), nullable=False)  # Mã therapist bên POS
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # Tên therapist
    gender: Mapped[str] = mapped_column(
        String(10), nullable=False  # 'male' hoặc 'female'
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False  # Còn làm việc không
    )

    shop = relationship("Shop", back_populates="therapists")
    shifts = relationship("TherapistShift", back_populates="therapist")
    reservations = relationship("Reservation", back_populates="therapist")

    def __repr__(self) -> str:
        return f"<Therapist {self.name} ({self.gender})>"
