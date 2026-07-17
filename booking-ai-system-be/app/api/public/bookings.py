from datetime import date

from fastapi import APIRouter, Depends, Header, Query
from app.core.exceptions import AppError
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.repositories import BookingRepository, ReservationRepository
from app.schemas.booking import (
    BookingCreate,
    PublicBookingListItem,
    BookingPatchInput,
    ReservationResponse,
)
from app.services import BookingService

router = APIRouter(prefix="/api/bookings", tags=["public-booking"])


# Tạo booking mới — yêu cầu Idempotency-Key để tránh trùng
@router.post("", status_code=201)
def create_booking(
    body: BookingCreate,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if not idempotency_key:
        raise AppError(400, code="MISSING_IDEMPOTENCY_KEY", detail="Thiếu Idempotency-Key header")

    service = BookingService(db)
    result = service.create(body, idempotency_key)
    return {"data": result}


# Danh sách booking công khai — lọc theo số điện thoại, mã POS, ngày, trạng thái (cursor-based)
@router.get("")
def list_bookings(
    pos_booking_code: str | None = Query(None),
    phone: str | None = Query(None),
    shop_id: str | None = Query(None),
    booking_date: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    db: Session = Depends(get_db),
):
    suid = parse_uuid(shop_id, "shop") if shop_id else None
    bd = date.fromisoformat(booking_date) if booking_date else None

    booking_repo = BookingRepository(db)
    bookings = booking_repo.find_public_all(
        pos_booking_code=pos_booking_code or None,
        phone=phone or None,
        shop_id=suid,
        booking_date=bd,
        status=status or None,
        limit=limit + 1,
    )

    has_more = len(bookings) > limit
    if has_more:
        bookings = bookings[:limit]

    return {
        "data": [PublicBookingListItem.model_validate(b).model_dump(mode="json") for b in bookings],
        "meta": {
            "limit": limit,
            "next_cursor": str(bookings[-1].booking_id) if has_more else None,
        },
    }


# Chi tiết booking công khai
@router.get("/{booking_id}")
def get_booking(booking_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(booking_id, "booking")
    service = BookingService(db)
    result = service.get(uid)
    return {"data": result}


# Cập nhật booking — huỷ, thay đổi thông tin
@router.patch("/{booking_id}")
def update_booking(booking_id: str, body: BookingPatchInput, db: Session = Depends(get_db)):
    uid = parse_uuid(booking_id, "booking")
    service = BookingService(db)
    result = service.update(uid, body)
    return {"data": result}


# Danh sách reservation của booking — thông tin therapist, course, giá
@router.get("/{booking_id}/reservations")
def list_reservations(booking_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(booking_id, "booking")
    booking_repo = BookingRepository(db)
    booking = booking_repo.find_by_id(uid)
    if not booking:
        raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")

    reservation_repo = ReservationRepository(db)
    reservations = reservation_repo.find_by_booking(uid)
    return {
        "data": [ReservationResponse.model_validate(r).model_dump(mode="json") for r in reservations],
    }
