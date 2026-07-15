from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, func, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Course(TimestampMixin, Base):
    __tablename__ = "courses"

    # pos_course_code là duy nhất trong phạm vi một shop
    __table_args__ = (
        Index("uq_course_per_shop", "shop_id", "pos_course_code", unique=True),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.shop_id"), nullable=False, index=True
    )
    pos_course_code: Mapped[str] = mapped_column(String(50), nullable=False)  # Mã dịch vụ bên POS
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # Tên dịch vụ
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)  # Thời lượng (phút)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # Giá tiền
    course_type: Mapped[str] = mapped_column(
        String(20), nullable=False  # 'main' (chính) hoặc 'addon' (bổ sung)
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False  # Còn kinh doanh không
    )

    shop = relationship("Shop", back_populates="courses")
    reservation_courses = relationship("ReservationCourse", back_populates="course")

    def __repr__(self) -> str:
        return f"<Course {self.name} - {self.course_type} - ¥{self.price}>"
