from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.exceptions import AppError


@dataclass(frozen=True)
class BookingStartWindow:
    start_at: datetime
    now: datetime
    earliest_allowed_at: datetime


# Lấy thời điểm UTC hiện tại qua một hàm riêng để nghiệp vụ thời gian có thể được cố định trong test.
def current_utc_time() -> datetime:
    return datetime.now(timezone.utc)


# Quy đổi ngày giờ tại timezone của shop sang UTC và tính mốc sớm nhất khách được phép đặt lịch.
def booking_start_window(
    booking_date: date,
    start_time: time,
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
    advance_minutes: int | None = None,
) -> BookingStartWindow:
    shop_timezone = ZoneInfo(timezone_name or settings.SHOP_TIMEZONE)
    current = now or current_utc_time()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    start_at = datetime.combine(booking_date, start_time, tzinfo=shop_timezone)
    current_utc = current.astimezone(timezone.utc)
    earliest_allowed_at = current_utc + timedelta(
        minutes=(
            settings.MINIMUM_BOOKING_ADVANCE_MINUTES
            if advance_minutes is None
            else advance_minutes
        )
    )
    return BookingStartWindow(
        start_at=start_at.astimezone(timezone.utc),
        now=current_utc,
        earliest_allowed_at=earliest_allowed_at,
    )


# Xác thực giờ bắt đầu không nằm trong quá khứ và đáp ứng số phút đặt trước tối thiểu.
def validate_booking_start(
    booking_date: date,
    start_time: time,
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
    advance_minutes: int | None = None,
) -> BookingStartWindow:
    window = booking_start_window(
        booking_date,
        start_time,
        now=now,
        timezone_name=timezone_name,
        advance_minutes=advance_minutes,
    )
    if window.start_at < window.now:
        raise AppError(
            422,
            code="BOOKING_START_IN_PAST",
            detail="Không thể tạo booking trong quá khứ",
            errors=[{"field": "start_time", "message": "Thời gian bắt đầu đã ở trong quá khứ"}],
        )
    if window.start_at < window.earliest_allowed_at:
        raise AppError(
            422,
            code="BOOKING_START_TOO_SOON",
            detail=(
                "Booking phải được tạo trước ít nhất "
                f"{settings.MINIMUM_BOOKING_ADVANCE_MINUTES if advance_minutes is None else advance_minutes} phút"
            ),
            errors=[{"field": "start_time", "message": "Thời gian bắt đầu quá sát giờ hiện tại"}],
        )
    return window


# Trả về boolean cho biết thời điểm bắt đầu đã vượt qua mốc đặt trước tối thiểu hay chưa.
def is_booking_start_allowed(
    booking_date: date,
    start_time: time,
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
    advance_minutes: int | None = None,
) -> bool:
    window = booking_start_window(
        booking_date,
        start_time,
        now=now,
        timezone_name=timezone_name,
        advance_minutes=advance_minutes,
    )
    return window.start_at >= window.earliest_allowed_at
