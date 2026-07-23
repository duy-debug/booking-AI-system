from datetime import date, time
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.repositories import (
    BookingRepository,
    ShiftRepository,
    ShopRepository,
    TherapistRepository,
)
from app.schemas.common import DataResponse
from app.schemas.schedule import ScheduleResponse


# Chuẩn hóa time hoặc chuỗi giờ thành HH:MM cho dữ liệu timeline.
def _to_hhmm(value: object) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)


# Xác định khoảng giờ có kết thúc ở ngày kế tiếp hay không.
def _spans_midnight(start: str, end: str) -> bool:
    try:
        start_hour, start_minute = (int(part) for part in start.split(":"))
        end_hour, end_minute = (int(part) for part in end.split(":"))
    except ValueError:
        return False
    return (end_hour * 60 + end_minute) < (start_hour * 60 + start_minute)


class ScheduleService:
    # Khởi tạo các repository chỉ đọc cần để tổng hợp timeline theo ngày.
    def __init__(self, session: Session):
        self.booking_repo = BookingRepository(session)
        self.shop_repo = ShopRepository(session)
        self.therapist_repo = TherapistRepository(session)
        self.shift_repo = ShiftRepository(session)

    # Tổng hợp shop, therapist, shift, vùng chặn và booking thành Pydantic response độc lập ORM.
    def get_daily_schedule(
        self,
        shop_id: UUID,
        schedule_date: date,
        view_from: str | None = None,
        view_to: str | None = None,
    ) -> DataResponse[ScheduleResponse]:
        shop = self.shop_repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

        therapists = self.therapist_repo.find_by_shop(shop_id)
        shifts = self.shift_repo.find_by_shop(shop_id, work_date=schedule_date)
        bookings = self.booking_repo.find_bookings_with_reservations(
            shop_id, schedule_date
        )

        active_shifts = [shift for shift in shifts if shift.is_active]
        if active_shifts:
            opens = min(_to_hhmm(shift.start_time) for shift in active_shifts)
            closes = max(_to_hhmm(shift.end_time) for shift in active_shifts)
        else:
            opens = settings.BUSINESS_HOURS_OPEN
            closes = settings.BUSINESS_HOURS_CLOSE

        business_hours = {
            "open": opens,
            "close": closes,
            "spans_midnight": _spans_midnight(opens, closes),
        }
        visible_from = view_from or opens
        visible_to = view_to or closes
        view_window = {
            "from": visible_from,
            "to": visible_to,
            "spans_midnight": _spans_midnight(visible_from, visible_to),
        }

        blocked_ranges = [
            {
                "therapist_id": shift.therapist_id,
                "therapist_name": shift.therapist.name if shift.therapist else None,
                "start_time": _to_hhmm(shift.start_time),
                "end_time": _to_hhmm(shift.end_time),
                "spans_midnight": _spans_midnight(
                    _to_hhmm(shift.start_time), _to_hhmm(shift.end_time)
                ),
                "reason": None,
            }
            for shift in shifts
            if not shift.is_active
        ]
        therapist_list = [
            {
                "therapist_id": therapist.therapist_id,
                "name": therapist.name,
                "gender": therapist.gender,
                "is_active": therapist.is_active,
            }
            for therapist in therapists
        ]
        shift_list = [
            {
                "shift_id": shift.shift_id,
                "therapist_id": shift.therapist_id,
                "therapist_name": shift.therapist.name if shift.therapist else None,
                "start_time": _to_hhmm(shift.start_time),
                "end_time": _to_hhmm(shift.end_time),
                "is_active": shift.is_active,
                "spans_midnight": _spans_midnight(
                    _to_hhmm(shift.start_time), _to_hhmm(shift.end_time)
                ),
            }
            for shift in shifts
        ]

        booking_list = []
        statuses: set[str] = set()
        for booking in bookings:
            statuses.add(booking.status)
            reservations = []
            for reservation in booking.reservations:
                reservations.append({
                    "reservation_id": reservation.reservation_id,
                    "person_index": reservation.person_index,
                    "therapist_id": reservation.therapist_id,
                    "therapist_name": (
                        reservation.therapist.name if reservation.therapist else None
                    ),
                    "start_time": _to_hhmm(reservation.start_time),
                    "end_time": _to_hhmm(reservation.end_time),
                    "status": reservation.status,
                    "assignment_source": getattr(
                        reservation, "assignment_source", "auto"
                    ),
                    "spans_midnight": _spans_midnight(
                        _to_hhmm(reservation.start_time),
                        _to_hhmm(reservation.end_time),
                    ),
                    "courses": [
                        {
                            "course_role": course.course_role,
                            "course_name_snapshot": course.course_name_snapshot,
                            "duration_snapshot": course.duration_snapshot,
                            "price_snapshot": course.price_snapshot,
                        }
                        for course in reservation.reservation_courses
                    ],
                })
            booking_list.append({
                "booking_id": booking.booking_id,
                "pos_booking_code": booking.pos_booking_code,
                "customer": (
                    {
                        "customer_id": booking.customer.customer_id,
                        "phone": booking.customer.phone,
                        "name": booking.customer.name,
                    }
                    if booking.customer
                    else None
                ),
                "booking_date": booking.booking_date,
                "start_time": _to_hhmm(booking.start_time),
                "end_time": _to_hhmm(booking.end_time),
                "status": booking.status,
                "number_of_people": booking.number_of_people,
                "total_duration_minutes": booking.total_duration_minutes,
                "therapist_request_type": booking.therapist_request_type,
                "requested_therapist_id": booking.requested_therapist_id,
                "spans_midnight": _spans_midnight(
                    _to_hhmm(booking.start_time), _to_hhmm(booking.end_time)
                ),
                "reservations": reservations,
            })

        response = ScheduleResponse.model_validate({
            "shop": {
                "shop_id": shop.shop_id,
                "name": shop.name,
                "timezone": settings.SHOP_TIMEZONE,
                "minimum_booking_advance_minutes": (
                    settings.MINIMUM_BOOKING_ADVANCE_MINUTES
                ),
                "therapist_break_minutes": getattr(
                    shop, "therapist_break_minutes", 0
                ),
                "business_hours": business_hours,
            },
            "date": schedule_date,
            "view_window": view_window,
            "therapists": therapist_list,
            "shifts": shift_list,
            "blocked_ranges": blocked_ranges,
            "bookings": booking_list,
            "booking_statuses": sorted(statuses),
        })
        return DataResponse(data=response)
