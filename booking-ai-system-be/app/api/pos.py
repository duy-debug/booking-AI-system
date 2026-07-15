# POS Webhook — endpoints dành cho POS gọi để đồng bộ dữ liệu
# POS gọi các endpoint này khi có thay đổi về booking code, availability, v.v.

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.core.exceptions import AppError
from app.db.models.booking import Booking

router = APIRouter(prefix="/api/pos", tags=["pos-webhook"])


class POSBookingSyncInput(BaseModel):
    # POS gửi khi xác nhận / cập nhật booking
    pos_booking_code: str = Field(..., min_length=1)
    local_booking_id: str | None = None  # UUID của booking trong hệ thống local
    status: str = Field(default="confirmed", pattern=r"^(confirmed|cancelled)$")
    pos_booking_date: str | None = None
    pos_start_time: str | None = None
    pos_end_time: str | None = None


class POSAvailabilityUpdateInput(BaseModel):
    # POS gửi khi availability thay đổi (tùy chọn)
    pos_shop_code: str
    booking_date: str
    start_time: str
    end_time: str
    available: bool


@router.post("/booking-sync")
def pos_booking_sync(body: POSBookingSyncInput, db: Session = Depends(get_db)):
    # POS xác nhận booking → cập nhật pos_booking_code trong hệ thống local
    booking = None

    # Tìm booking theo local_booking_id trước
    if body.local_booking_id:
        uid = parse_uuid(body.local_booking_id, "booking")
        booking = db.get(Booking, uid)

    # Fallback: tìm theo pos_booking_code
    if not booking:
        booking = db.scalar(
            select(Booking).where(Booking.pos_booking_code == body.pos_booking_code)
        )

    if not booking:
        raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking để đồng bộ")

    # Cập nhật thông tin từ POS
    booking.pos_booking_code = body.pos_booking_code
    booking.pos_sync_status = "synced"

    if body.status == "cancelled":
        booking.status = "cancelled"
        booking.pos_sync_status = "cancelled"

    db.commit()
    db.refresh(booking)

    return {"message": "Booking synced successfully", "booking_id": str(booking.booking_id)}


@router.post("/availability-update")
def pos_availability_update(body: POSAvailabilityUpdateInput):
    # POS gửi cập nhật availability (ví dụ: slot vừa bị chiếm)
    # Hiện tại chỉ ghi log — có thể mở rộng sau để cache hoặc invalidate cache
    return {"message": "Availability update received"}
