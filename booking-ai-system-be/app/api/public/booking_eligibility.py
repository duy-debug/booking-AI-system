from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.booking import BookingEligibilityCheckInput
from app.services import EligibilityService

router = APIRouter(prefix="/api/booking-eligibility-checks", tags=["public-booking"])


# Kiểm tra khách hàng có đủ điều kiện đặt lịch — NG list, giới hạn số lần
@router.post("", status_code=201)
def check_eligibility(body: BookingEligibilityCheckInput, db: Session = Depends(get_db)):
    service = EligibilityService(db)
    result = service.check_eligibility(phone=body.phone, shop_id=body.shop_id)
    return {"data": result}
