import logging
from datetime import date

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.core.exceptions import AppError
from app.infrastructure.logging_config import log_event
from app.schemas.booking import (
    BookingCreate,
    BookingLookupInput,
    BookingPatchInput,
    PublicBookingListItem,
    PublicBookingResponse,
    ReservationResponse,
)
from app.schemas.common import CollectionResponse, DataResponse, PaginatedResponse
from app.services import BookingQueryService, BookingService

router = APIRouter(prefix="/api/bookings", tags=["public-booking"])


# Tạo booking mới — yêu cầu Idempotency-Key để tránh trùng
@router.post("", status_code=201, response_model=DataResponse[PublicBookingResponse])
def create_booking(
    body: BookingCreate,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if not idempotency_key:
        raise AppError(400, code="MISSING_IDEMPOTENCY_KEY", detail="Thiếu Idempotency-Key header")

    service = BookingService(db)
    result = PublicBookingResponse.model_validate(service.create(body, idempotency_key))
    log_event(
        logging.DEBUG,
        "BookingService",
        "pos_business_rules_checked",
        operation="create_booking",
        rules=[
            "idempotency_checked",
            "shop_and_courses_valid",
            "slot_available",
            "group_therapist_rule_valid",
        ],
        status="passed",
        reservation_count=len(result.reservations),
    )
    return DataResponse(data=result)


# Tra cứu booking bằng ID và số điện thoại mà không cần OTP.
@router.post("/lookup", response_model=DataResponse[PublicBookingResponse])
def lookup_booking(body: BookingLookupInput, db: Session = Depends(get_db)):
    service = BookingQueryService(db)
    return service.lookup_public(body.booking_id, body.phone)


# Danh sách booking công khai — lọc theo số điện thoại, mã POS, ngày, trạng thái (cursor-based)
@router.get("", response_model=PaginatedResponse[PublicBookingListItem])
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

    service = BookingQueryService(db)
    return service.list_public(
        pos_booking_code=pos_booking_code or None,
        phone=phone or None,
        shop_id=suid,
        booking_date=bd,
        status=status or None,
        limit=limit,
        cursor=cursor,
    )


# Chi tiết booking công khai
@router.get("/{booking_id}", response_model=DataResponse[PublicBookingResponse])
def get_booking(booking_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(booking_id, "booking")
    service = BookingQueryService(db)
    return service.get_public_detail(uid)


# Cập nhật booking — huỷ, thay đổi thông tin
@router.patch("/{booking_id}", response_model=DataResponse[PublicBookingResponse])
def update_booking(booking_id: str, body: BookingPatchInput, db: Session = Depends(get_db)):
    uid = parse_uuid(booking_id, "booking")
    service = BookingService(db)
    result = PublicBookingResponse.model_validate(service.update(uid, body))
    return DataResponse(data=result)


# Danh sách reservation của booking — thông tin therapist, course, giá
@router.get(
    "/{booking_id}/reservations",
    response_model=CollectionResponse[ReservationResponse],
)
def list_reservations(booking_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(booking_id, "booking")
    service = BookingQueryService(db)
    return service.list_reservations(uid)
