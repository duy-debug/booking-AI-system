from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, ForeignKey, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class TherapistShift(TimestampMixin, Base):
    __tablename__ = "therapist_shifts"

    shift_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.therapist_id"), nullable=False, index=True
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.shop_id"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)  # Ngày làm việc
    start_time: Mapped[time] = mapped_column(Time, nullable=False)  # Giờ bắt đầu ca
    end_time: Mapped[time] = mapped_column(Time, nullable=False)  # Giờ kết thúc ca
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False  # Ca còn hiệu lực không
    )

    therapist = relationship("Therapist", back_populates="shifts")
    shop = relationship("Shop", back_populates="therapist_shifts")

    # Tạo chuỗi đại diện cho ngày và khung giờ của ca làm việc khi debug.
    def __repr__(self) -> str:
        return f"<Shift {self.work_date} {self.start_time}-{self.end_time}>"
