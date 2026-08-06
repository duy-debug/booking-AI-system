# Repository cho Booking — truy vấn booking và eager-load relationship cần thiết,
# chỉ thực hiện data access và không chứa business logic.
import logging
from datetime import date
from time import perf_counter
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, joinedload

from app.db.models.booking import Booking
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.infrastructure.logging_config import log_event


class BookingRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Booking trong shop theo ngày — eager load reservations + therapist + courses (1 query)
    # Trả về TẤT CẢ booking (kể cả cancelled) để client tự lọc theo status.
    def find_bookings_with_reservations(
        self, shop_id, work_date: date
    ) -> list[Booking]:
        stmt = (
            select(Booking)
            .where(
                Booking.shop_id == shop_id,
                Booking.booking_date == work_date,
            )
            .options(
                joinedload(Booking.reservations)
                .joinedload(Reservation.therapist),
                joinedload(Booking.reservations)
                .joinedload(Reservation.reservation_courses),
                joinedload(Booking.customer),
                joinedload(Booking.shop),
            )
            .order_by(Booking.start_time)
        )
        return list(self.session.scalars(stmt).unique().all())

    # Tìm booking theo ID — eager load reservations + courses + customer
    def find_by_id(self, booking_id: UUID) -> Booking | None:
        stmt = (
            select(Booking)
            .where(Booking.booking_id == booking_id)
            .options(
                joinedload(Booking.reservations)
                .joinedload(Reservation.therapist),
                joinedload(Booking.reservations)
                .joinedload(Reservation.reservation_courses),
                joinedload(Booking.customer),
                joinedload(Booking.shop),
            )
        )
        return self.session.scalar(stmt)

    # Tìm booking theo ID và số điện thoại của customer để bảo vệ luồng tra cứu công khai.
    def find_by_id_and_phone(self, booking_id: UUID, phone: str) -> Booking | None:
        stmt = (
            select(Booking)
            .where(
                Booking.booking_id == booking_id,
                Booking.customer.has(phone=phone),
            )
            .options(
                joinedload(Booking.reservations)
                .joinedload(Reservation.therapist),
                joinedload(Booking.reservations)
                .joinedload(Reservation.reservation_courses),
                joinedload(Booking.customer),
                joinedload(Booking.shop),
            )
        )
        return self.session.scalar(stmt)

    # Danh sách booking public — lọc theo phone, shop, ngày, status (cursor-based)
    def find_public_all(
        self,
        pos_booking_code: str | None = None,
        phone: str | None = None,
        shop_id: UUID | None = None,
        booking_date: date | None = None,
        status: str | None = None,
        limit: int = 20,
        cursor: UUID | None = None,
    ) -> list[Booking]:
        stmt = select(Booking).options(joinedload(Booking.customer))
        if pos_booking_code:
            stmt = stmt.where(Booking.pos_booking_code == pos_booking_code)
        if phone:
            stmt = stmt.join(Booking.customer).where(Booking.customer.has(phone=phone))
        if shop_id:
            stmt = stmt.where(Booking.shop_id == shop_id)
        if booking_date:
            stmt = stmt.where(Booking.booking_date == booking_date)
        if status:
            stmt = stmt.where(Booking.status == status)
        stmt = self._apply_cursor(stmt, cursor)
        stmt = stmt.order_by(Booking.created_at.desc(), Booking.booking_id.desc()).limit(limit)
        return list(self.session.scalars(stmt).unique().all())

    # Danh sách booking admin — lọc theo các trường quản trị và eager-load customer để tránh N+1.
    def find_admin_all(
        self,
        *,
        shop_id: UUID | None = None,
        booking_date: date | None = None,
        status: str | None = None,
        phone: str | None = None,
        pos_booking_code: str | None = None,
        limit: int = 20,
        cursor: UUID | None = None,
    ) -> list[Booking]:
        stmt = select(Booking).options(joinedload(Booking.customer))
        if shop_id:
            stmt = stmt.where(Booking.shop_id == shop_id)
        if booking_date:
            stmt = stmt.where(Booking.booking_date == booking_date)
        if status:
            stmt = stmt.where(Booking.status == status)
        if phone:
            stmt = stmt.where(Booking.customer.has(phone=phone))
        if pos_booking_code:
            stmt = stmt.where(Booking.pos_booking_code == pos_booking_code)
        stmt = self._apply_cursor(stmt, cursor)
        stmt = stmt.order_by(Booking.created_at.desc(), Booking.booking_id.desc()).limit(limit)
        return list(self.session.scalars(stmt).unique().all())

    # Áp dụng cursor theo cặp created_at và booking_id để phân trang ổn định khi nhiều booking cùng thời điểm.
    def _apply_cursor(self, stmt, cursor: UUID | None):
        if cursor is None:
            return stmt
        cursor_booking = self.find_by_id(cursor)
        if cursor_booking is None:
            return stmt.where(False)
        return stmt.where(
            tuple_(Booking.created_at, Booking.booking_id)
            < tuple_(cursor_booking.created_at, cursor_booking.booking_id)
        )

    # Booking không cancelled trong shop theo ngày — cho availability check
    def find_by_shop_date_non_cancelled(self, shop_id: UUID, booking_date: date) -> list[Booking]:
        stmt = (
            select(Booking)
            .where(
                Booking.shop_id == shop_id,
                Booking.booking_date == booking_date,
                Booking.status != "cancelled",
            )
        )
        return list(self.session.scalars(stmt).all())

    # Tìm booking theo idempotency_key — chống tạo trùng
    def find_by_idempotency_key(self, idempotency_key: str) -> Booking | None:
        from uuid import UUID
        try:
            key_uuid = UUID(idempotency_key)
        except ValueError:
            return None
        started = perf_counter()
        stmt = select(Booking).where(Booking.idempotency_key == key_uuid)
        result = self.session.scalar(stmt)
        log_event(
            logging.DEBUG,
            "BookingRepository",
            "database_operation_completed",
            operation="find_by_idempotency_key",
            row_count=1 if result is not None else 0,
            duration_ms=round((perf_counter() - started) * 1000),
        )
        return result

    # Lưu booking mới — add + flush
    def save(self, booking: Booking) -> Booking:
        started = perf_counter()
        self.session.add(booking)
        self.session.flush()
        log_event(
            logging.DEBUG,
            "BookingRepository",
            "database_operation_completed",
            operation="save_booking",
            row_count=1,
            duration_ms=round((perf_counter() - started) * 1000),
        )
        return booking

    # Xóa booking theo ID (dùng cho hủy)
    def delete(self, booking_id: UUID) -> None:
        stmt = select(Booking).where(Booking.booking_id == booking_id)
        booking = self.session.scalar(stmt)
        if booking:
            self.session.delete(booking)
            self.session.flush()
