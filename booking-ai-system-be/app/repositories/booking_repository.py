# Repository cho Booking — CRUD + tra cứu booking theo nhiều tiêu chí (admin/public)
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models.booking import Booking
from app.db.models.customer import Customer


class BookingRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Tìm booking theo ID
    def find_by_id(self, booking_id: UUID) -> Booking | None:
        return self.session.get(Booking, booking_id)

    # Tìm booking theo idempotency_key (tránh tạo trùng)
    def find_by_idempotency_key(self, key: str) -> Booking | None:
        stmt = select(Booking).where(Booking.idempotency_key == key)
        return self.session.scalar(stmt)

    # Danh sách booking cho admin — lọc theo shop, ngày, trạng thái, phone, mã POS
    def find_admin_all(
        self,
        shop_id: UUID | None = None,
        booking_date: date | None = None,
        status: str | None = None,
        phone: str | None = None,
        pos_booking_code: str | None = None,
        limit: int = 20,
    ) -> list[Booking]:
        stmt = select(Booking).options(joinedload(Booking.customer))
        if shop_id is not None:
            stmt = stmt.where(Booking.shop_id == shop_id)
        if booking_date is not None:
            stmt = stmt.where(Booking.booking_date == booking_date)
        if status is not None:
            stmt = stmt.where(Booking.status == status)
        if phone is not None:
            stmt = stmt.join(Customer).where(Customer.phone == phone)
        if pos_booking_code is not None:
            stmt = stmt.where(Booking.pos_booking_code == pos_booking_code)
        stmt = stmt.order_by(Booking.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).unique().all())

    # Danh sách booking cho public — lọc theo mã POS, phone, shop, ngày, trạng thái
    def find_public_all(
        self,
        pos_booking_code: str | None = None,
        phone: str | None = None,
        shop_id: UUID | None = None,
        booking_date: date | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Booking]:
        stmt = select(Booking)
        if pos_booking_code is not None:
            stmt = stmt.where(Booking.pos_booking_code == pos_booking_code)
        if phone is not None:
            stmt = stmt.join(Customer).where(Customer.phone == phone)
        if shop_id is not None:
            stmt = stmt.where(Booking.shop_id == shop_id)
        if booking_date is not None:
            stmt = stmt.where(Booking.booking_date == booking_date)
        if status is not None:
            stmt = stmt.where(Booking.status == status)
        stmt = stmt.order_by(Booking.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    # Booking trong shop theo ngày — loại trừ cancelled (dùng cho kiểm tra slot)
    def find_by_shop_date_non_cancelled(self, shop_id: UUID, booking_date: date) -> list[Booking]:
        stmt = select(Booking).where(
            Booking.shop_id == shop_id,
            Booking.booking_date == booking_date,
            Booking.status != "cancelled",
        )
        return list(self.session.scalars(stmt).all())

    # Lưu booking mới — add + flush
    def save(self, booking: Booking) -> Booking:
        self.session.add(booking)
        self.session.flush()
        return booking
