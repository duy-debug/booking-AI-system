from datetime import date, time

# Service tổng hợp lịch theo ngày nghiệp vụ (resource timeline).
# Quản lý orchestration + transaction, KHÔNG chứa business rule phân tán (nguyên tắc 3).
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.repositories import BookingRepository, ShopRepository


def _to_hhmm(value) -> str:
    # time/Time -> "HH:MM" (bỏ giây)
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)


def _spans_midnight(start: str, end: str) -> bool:
    # So sánh "HH:MM": nếu end < start => qua nửa đêm
    try:
        sh, sm = (int(x) for x in start.split(":"))
        eh, em = (int(x) for x in end.split(":"))
    except ValueError:
        return False
    return (eh * 60 + em) < (sh * 60 + sm)


class BookingService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.schedule_repo = BookingRepository(session)
        self.shop_repo = ShopRepository(session)

    # Lấy toàn bộ dữ liệu timeline trong một ngày nghiệp vụ, gom 1 request.
    def get_schedule(
        self,
        shop_id,
        schedule_date: date,
        view_from: str | None = None,
        view_to: str | None = None,
    ) -> dict:
        shop = self.shop_repo.find_by_id(shop_id)
        if not shop:
            raise AppError(404, code="SHOP_NOT_FOUND", detail="Khong tim thay shop")

        therapists = self.schedule_repo.find_therapists_by_shop(shop_id)
        shifts = self.schedule_repo.find_shifts(shop_id, schedule_date)
        bookings = self.schedule_repo.find_bookings_with_reservations(
            shop_id, schedule_date
        )

        # Khung giờ hoạt động (business hours) = min/max ca active trong ngày.
        active_shifts = [s for s in shifts if s.is_active]
        if active_shifts:
            opens = min(_to_hhmm(s.start_time) for s in active_shifts)
            closes = max(_to_hhmm(s.end_time) for s in active_shifts)
        else:
            opens = settings.BUSINESS_HOURS_OPEN
            closes = settings.BUSINESS_HOURS_CLOSE
        business_hours = {
            "open": opens,
            "close": closes,
            "spans_midnight": _spans_midnight(opens, closes),
        }

        # Cửa sổ hiển thị (view window) do client truyền, mặc định = business hours.
        v_from = view_from or opens
        v_to = view_to or closes
        view_window = {
            "from": v_from,
            "to": v_to,
            "spans_midnight": _spans_midnight(v_from, v_to),
        }

        # Blocked ranges: ánh xạ các ca INACTIVE thành đoạn bị chặn của therapist.
        # (Hiện tại DB chưa có bảng blocked_ranges riêng; dùng inactive shift thay thế.
        #  Khuyến nghị: bổ sung bảng blocked_ranges trong migration sau.)
        blocked_ranges = [
            {
                "therapist_id": str(s.therapist_id),
                "therapist_name": s.therapist.name if s.therapist else None,
                "start_time": _to_hhmm(s.start_time),
                "end_time": _to_hhmm(s.end_time),
                "spans_midnight": _spans_midnight(
                    _to_hhmm(s.start_time), _to_hhmm(s.end_time)
                ),
                "reason": None,
            }
            for s in shifts
            if not s.is_active
        ]

        therapist_list = [
            {
                "therapist_id": str(t.therapist_id),
                "name": t.name,
                "gender": t.gender,
                "is_active": t.is_active,
            }
            for t in therapists
        ]

        shift_list = [
            {
                "shift_id": str(s.shift_id),
                "therapist_id": str(s.therapist_id),
                "therapist_name": s.therapist.name if s.therapist else None,
                "start_time": _to_hhmm(s.start_time),
                "end_time": _to_hhmm(s.end_time),
                "is_active": s.is_active,
                "spans_midnight": _spans_midnight(
                    _to_hhmm(s.start_time), _to_hhmm(s.end_time)
                ),
            }
            for s in shifts
        ]

        booking_list = []
        statuses: set[str] = set()
        for b in bookings:
            statuses.add(b.status)
            res_list = []
            for res in b.reservations:
                courses = [
                    {
                        "course_role": c.course_role,
                        "course_name_snapshot": c.course_name_snapshot,
                        "duration_snapshot": c.duration_snapshot,
                        "price_snapshot": float(c.price_snapshot),
                    }
                    for c in res.reservation_courses
                ]
                res_list.append({
                    "reservation_id": str(res.reservation_id),
                    "person_index": res.person_index,
                    "therapist_id": str(res.therapist_id),
                    "therapist_name": res.therapist.name if res.therapist else None,
                    "start_time": _to_hhmm(res.start_time),
                    "end_time": _to_hhmm(res.end_time),
                    "status": res.status,
                    "spans_midnight": _spans_midnight(
                        _to_hhmm(res.start_time), _to_hhmm(res.end_time)
                    ),
                    "courses": courses,
                })
            booking_list.append({
                "booking_id": str(b.booking_id),
                "pos_booking_code": b.pos_booking_code,
                "customer": {
                    "customer_id": str(b.customer.customer_id) if b.customer else None,
                    "phone": b.customer.phone if b.customer else None,
                    "name": b.customer.name if b.customer else None,
                },
                "booking_date": b.booking_date.isoformat(),
                "start_time": _to_hhmm(b.start_time),
                "end_time": _to_hhmm(b.end_time),
                "status": b.status,
                "number_of_people": b.number_of_people,
                "total_duration_minutes": b.total_duration_minutes,
                "therapist_request_type": b.therapist_request_type,
                "requested_therapist_id": (
                    str(b.requested_therapist_id) if b.requested_therapist_id else None
                ),
                "spans_midnight": _spans_midnight(
                    _to_hhmm(b.start_time), _to_hhmm(b.end_time)
                ),
                "reservations": res_list,
            })

        return {
            "shop": {
                "shop_id": str(shop.shop_id),
                "name": shop.name,
                "timezone": settings.SHOP_TIMEZONE,
                "business_hours": business_hours,
            },
            "date": schedule_date.isoformat(),
            "view_window": view_window,
            "therapists": therapist_list,
            "shifts": shift_list,
            "blocked_ranges": blocked_ranges,
            "bookings": booking_list,
            "booking_statuses": sorted(statuses),
        }
