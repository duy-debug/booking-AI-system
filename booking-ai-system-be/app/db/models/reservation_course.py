from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReservationCourse(Base):
    # Không kế thừa TimestampMixin vì chỉ cần created_at (snapshot không sửa)
    __tablename__ = "reservation_courses"

    reservation_course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reservations.reservation_id"), nullable=False,
        index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.course_id"), nullable=False, index=True
    )
    course_role: Mapped[str] = mapped_column(
        String(20), nullable=False  # 'main' (chính) hoặc 'addon' (bổ sung)
    )
    duration_snapshot: Mapped[int] = mapped_column(
        Integer, nullable=False  # Thời lượng tại thời điểm đặt
    )
    price_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False  # Giá tại thời điểm đặt
    )
    course_name_snapshot: Mapped[str] = mapped_column(
        String(255), nullable=False  # Tên dịch vụ tại thời điểm đặt
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    reservation = relationship("Reservation", back_populates="reservation_courses")
    course = relationship("Course", back_populates="reservation_courses")

    def __repr__(self) -> str:
        return f"<ReservationCourse {self.course_role} - {self.course_name_snapshot}>"
