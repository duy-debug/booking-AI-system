# Repository cho Schedule (admin) — truy vấn tổng hợp một ngày nghiệp vụ
# chỉ làm data access, KHÔNG chứa business logic (nguyên tắc 4).
# Dùng joinedload để tránh N+1 query khi build timeline.
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models.booking import Booking
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.db.models.therapist import Therapist
from app.db.models.therapist_shift import TherapistShift


class BookingRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Shop theo ID
    def find_shop(self, shop_id) -> object | None:
        from app.db.models.shop import Shop

        return self.session.get(Shop, shop_id)

    # Toàn bộ therapist của shop (kể cả không có ca) — để vẽ đủ resource row
    def find_therapists_by_shop(self, shop_id) -> list[Therapist]:
        stmt = (
            select(Therapist)
            .where(Therapist.shop_id == shop_id)
            .order_by(Therapist.name)
        )
        return list(self.session.scalars(stmt).all())

    # Ca làm việc trong shop theo ngày — kèm therapist (1 query, eager)
    def find_shifts(self, shop_id, work_date: date) -> list[TherapistShift]:
        stmt = (
            select(TherapistShift)
            .where(
                TherapistShift.shop_id == shop_id,
                TherapistShift.work_date == work_date,
            )
            .options(joinedload(TherapistShift.therapist))
            .order_by(TherapistShift.start_time)
        )
        return list(self.session.scalars(stmt).all())

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
            )
            .order_by(Booking.start_time)
        )
        return list(self.session.scalars(stmt).unique().all())
