from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.core.auth import require_admin
from app.core.exceptions import AppError
from app.services.booking_service import BookingService

# Endpoint tổng hợp cho màn hình resource timeline (schedule).
# 1 request trả về shop + therapists + shifts + blocked ranges + bookings + statuses + business hours.
router = APIRouter(prefix="/api/admin/booking", tags=["admin-booking"], dependencies=[Depends(require_admin)])


@router.get("")
def get_schedule(
    shop_id: str = Query(..., description="ID shop (bắt buộc)"),
    booking_date: str = Query(..., alias="date", description="Ngày nghiệp vụ YYYY-MM-DD"),
    view_from: str | None = Query(None, alias="from", description="Đầu cửa sổ hiển thị HH:MM"),
    view_to: str | None = Query(None, alias="to", description="Cuối cửa sổ hiển thị HH:MM"),
    db: Session = Depends(get_db),
):
    uid = parse_uuid(shop_id, "shop")

    try:
        parsed_date = date.fromisoformat(booking_date)
    except ValueError:
        raise AppError(
            400,
            code="INVALID_QUERY_PARAMETER",
            detail="date không đúng format YYYY-MM-DD",
        )

    for label, value in (("from", view_from), ("to", view_to)):
        if value is not None and not _is_hhmm(value):
            raise AppError(
                400,
                code="INVALID_QUERY_PARAMETER",
                detail=f"{label} không đúng format HH:MM",
            )

    service = BookingService(db)
    data = service.get_schedule(uid, parsed_date, view_from=view_from, view_to=view_to)
    return {"data": data}


def _is_hhmm(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = (int(p) for p in parts)
    except ValueError:
        return False
    return 0 <= h <= 23 and 0 <= m <= 59
