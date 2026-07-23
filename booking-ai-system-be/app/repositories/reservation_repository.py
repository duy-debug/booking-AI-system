# Repository cho Reservation — CRUD + kiểm tra overlap, tra cứu theo booking/therapist
from datetime import date, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models.booking import Booking
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.core.time_ranges import expand_time_window


class ReservationRepository:
    # Khởi tạo với session database
    def __init__(self, session: Session):
        self.session = session

    # Danh sách reservation theo booking — sắp xếp theo person_index
    def find_by_booking(self, booking_id: UUID) -> list[Reservation]:
        stmt = (
            select(Reservation)
            .where(Reservation.booking_id == booking_id)
            .options(
                joinedload(Reservation.therapist),
                joinedload(Reservation.reservation_courses),
            )
            .order_by(Reservation.person_index)
        )
        return list(self.session.scalars(stmt).unique().all())

    # Reservation không cancelled trong shop theo ngày
    def find_by_shop_date_non_cancelled(self, shop_id: UUID, booking_date: date) -> list[Reservation]:
        stmt = (
            select(Reservation)
            .join(Booking)
            .where(
                Booking.shop_id == shop_id,
                Booking.booking_date == booking_date,
                Booking.status != "cancelled",
            )
        )
        return list(self.session.scalars(stmt).all())

    # Reservation của therapist theo ngày — loại trừ cancelled, sắp xếp theo giờ
    def find_by_therapist_and_date(self, therapist_id: UUID, booking_date: date) -> list[Reservation]:
        stmt = (
            select(Reservation)
            .join(Booking)
            .where(
                Reservation.therapist_id == therapist_id,
                Booking.booking_date == booking_date,
                Booking.status != "cancelled",
            )
            .order_by(Reservation.start_time)
        )
        return list(self.session.scalars(stmt).all())

    # Kiểm tra therapist đã có reservation trong khung giờ chưa
    def exists_overlap(
        self,
        therapist_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        exclude_booking_id: UUID | None = None,
        break_minutes: int = 0,
    ) -> bool:
        overlap_start, overlap_end = expand_time_window(
            start_time, end_time, break_minutes
        )
        stmt = (
            select(Reservation.reservation_id)
            .join(Booking)
            .where(
                Reservation.therapist_id == therapist_id,
                Booking.booking_date == booking_date,
                Booking.status != "cancelled",
                Reservation.start_time < overlap_end,
                Reservation.end_time > overlap_start,
            )
        )
        if exclude_booking_id is not None:
            stmt = stmt.where(Booking.booking_id != exclude_booking_id)
        stmt = stmt.limit(1)
        return self.session.scalar(stmt) is not None

    # Tìm và khóa các reservation active đang chiếm therapist trong khoảng giờ để tái cân bằng an toàn.
    def find_overlaps_for_update(
        self,
        therapist_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        break_minutes: int = 0,
    ) -> list[Reservation]:
        overlap_start, overlap_end = expand_time_window(
            start_time, end_time, break_minutes
        )
        stmt = (
            select(Reservation)
            .join(Booking)
            .where(
                Reservation.therapist_id == therapist_id,
                Booking.booking_date == booking_date,
                Booking.status != "cancelled",
                Reservation.start_time < overlap_end,
                Reservation.end_time > overlap_start,
            )
            .options(joinedload(Reservation.booking))
            .order_by(Reservation.reservation_id)
            .with_for_update(of=Reservation)
        )
        return list(self.session.scalars(stmt).all())

    # Tìm các reservation active bị giao với khoảng giờ nhưng không khóa dòng, phù hợp cho bước dự báo.
    def find_overlaps(
        self,
        therapist_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        break_minutes: int = 0,
    ) -> list[Reservation]:
        overlap_start, overlap_end = expand_time_window(
            start_time, end_time, break_minutes
        )
        stmt = (
            select(Reservation)
            .join(Booking)
            .where(
                Reservation.therapist_id == therapist_id,
                Booking.booking_date == booking_date,
                Booking.status != "cancelled",
                Reservation.start_time < overlap_end,
                Reservation.end_time > overlap_start,
            )
            .options(joinedload(Reservation.booking))
            .order_by(Reservation.reservation_id)
        )
        return list(self.session.scalars(stmt).all())

    # Kiểm tra xung đột slot — có reservation nào trong khung giờ không
    def exists_slot_conflict(
        self,
        shop_id: UUID,
        booking_date: date,
        start_time: time,
        end_time: time,
        break_minutes: int = 0,
    ) -> bool:
        overlap_start, overlap_end = expand_time_window(
            start_time, end_time, break_minutes
        )
        stmt = (
            select(Reservation.reservation_id)
            .join(Booking)
            .where(
                Booking.shop_id == shop_id,
                Booking.booking_date == booking_date,
                Booking.status != "cancelled",
                Reservation.start_time < overlap_end,
                Reservation.end_time > overlap_start,
            )
            .limit(1)
        )
        return self.session.scalar(stmt) is not None

    # Danh sách course gắn với reservation
    def find_courses_by_reservation(self, reservation_id: UUID) -> list[ReservationCourse]:
        stmt = select(ReservationCourse).where(ReservationCourse.reservation_id == reservation_id)
        return list(self.session.scalars(stmt).all())

    # Lưu reservation mới — add + flush
    def save(self, reservation: Reservation) -> Reservation:
        self.session.add(reservation)
        self.session.flush()
        return reservation

    # Lưu course snapshot của reservation và flush để dữ liệu sẵn sàng trong transaction hiện tại.
    def save_course(self, course: ReservationCourse) -> ReservationCourse:
        self.session.add(course)
        self.session.flush()
        return course

    # Xóa reservation; cascade của ORM sẽ xóa các course snapshot liên quan.
    def delete(self, reservation: Reservation) -> None:
        self.session.delete(reservation)
        self.session.flush()
