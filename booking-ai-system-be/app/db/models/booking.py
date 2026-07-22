from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.shop_id"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    # DEPRECATED: hai cột này từng dùng cho POS integration.
    # Sẽ xoá trong migration riêng sau khi backend-chatbot tách ổn định.
    # Call site vẫn dùng: admin/public bookings API (filter + response),
    # schema booking.py (response models), alembic migrations (lịch sử).
    pos_booking_code: Mapped[str | None] = mapped_column(
        String(50), unique=True, index=True
    )
    pos_sync_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)  # Ngày đặt
    start_time: Mapped[time] = mapped_column(Time, nullable=False)  # Giờ bắt đầu
    end_time: Mapped[time] = mapped_column(Time, nullable=False)  # Giờ kết thúc
    number_of_people: Mapped[int] = mapped_column(
        Integer, nullable=False  # Số người (1-3)
    )
    total_duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False  # Tổng thời lượng (phút)
    )
    status: Mapped[str] = mapped_column(
        String(30), default="confirmed", nullable=False  # confirmed, cancelled, ...
    )
    therapist_request_type: Mapped[str] = mapped_column(
        String(20), default="none", nullable=False  # none, specific, gender
    )
    requested_therapist_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("therapists.therapist_id"), nullable=True,
        index=True  # Therapist được chỉ định (nếu có)
    )
    requested_gender: Mapped[str | None] = mapped_column(
        String(10)  # Giới tính therapist yêu cầu
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False  # Key chống tạo trùng booking
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(500))  # Lý do hủy
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)  # Thời điểm hủy
    )

    shop = relationship("Shop", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookings")
    reservations = relationship(
        "Reservation", back_populates="booking", cascade="all, delete-orphan"
    )

    # Tạo chuỗi đại diện ngắn gọn cho booking khi debug hoặc ghi log trong SQLAlchemy.
    def __repr__(self) -> str:
        return f"<Booking {self.pos_booking_code} - {self.status}>"
