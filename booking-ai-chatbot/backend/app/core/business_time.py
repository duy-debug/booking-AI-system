from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

FIXED_TIMEZONE_OFFSETS = {
    "UTC": 0,
    "Etc/UTC": 0,
    "Asia/Ho_Chi_Minh": 7,
    "Asia/Bangkok": 7,
    "Asia/Tokyo": 9,
}


def resolve_timezone(timezone_name: str) -> tzinfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        offset = FIXED_TIMEZONE_OFFSETS.get(timezone_name)
        if offset is None:
            raise
        return timezone(timedelta(hours=offset), name=timezone_name)


def business_today() -> date:
    return datetime.now(resolve_timezone(settings.BUSINESS_TIMEZONE)).date()
