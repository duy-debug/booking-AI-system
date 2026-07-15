from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import ForeignKey, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Reservation(TimestampMixin, Base):
    __tablename__ = "reservations"

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.booking_id"), nullable=False, index=True
    )
    person_index: Mapped[int] = mapped_column(
        Integer, nullable=False  # Thứ tự người trong nhóm (1, 2, 3)
    )
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.therapist_id"), nullable=False, index=True
    )
    start_time: Mapped[time] = mapped_column(Time, nullable=False)  # Giờ bắt đầu riêng
    end_time: Mapped[time] = mapped_column(Time, nullable=False)  # Giờ kết thúc riêng
    status: Mapped[str] = mapped_column(
        String(30), default="assigned", nullable=False  # assigned, ...
    )

    booking = relationship("Booking", back_populates="reservations")
    therapist = relationship("Therapist", back_populates="reservations")
    reservation_courses = relationship(
        "ReservationCourse",
        back_populates="reservation",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Reservation #{self.person_index} - {self.status}>"
