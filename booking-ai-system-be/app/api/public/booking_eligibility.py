# Public — Booking Eligibility Check (kiểm tra phone có bị cấm không)

import uuid

from fastapi import APIRouter, Depends
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.api.schemas.booking import BookingEligibilityCheckInput, BookingEligibilityCheckResponse
from app.db.models.customer import Customer
from app.db.models.customer_restriction import CustomerRestriction
from app.db.models.shop import Shop

router = APIRouter(prefix="/api/booking-eligibility-checks", tags=["public-booking"])


@router.post("", status_code=201)
def check_eligibility(body: BookingEligibilityCheckInput, db: Session = Depends(get_db)):
    # Kiểm tra phone có được phép đặt booking không
    # Check shop
    shop = db.get(Shop, body.shop_id)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
    if not shop.is_active:
        raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

    # Check NG list
    restriction = db.scalar(
        select(CustomerRestriction).where(
            CustomerRestriction.phone == body.phone,
            CustomerRestriction.is_active == True,
        )
    )
    if restriction:
        raise AppError(403, code="CUSTOMER_IN_NG_LIST", detail="Số điện thoại này không được phép đặt booking")

    # Tìm customer
    customer = db.scalar(select(Customer).where(Customer.phone == body.phone))

    return {
        "data": BookingEligibilityCheckResponse(
            check_id=uuid.uuid4(),
            phone=body.phone,
            eligible=True,
            customer={
                "customer_type": "existing" if customer else "new",
                "customer_id": str(customer.customer_id) if customer else None,
                "name": customer.name if customer else None,
                "is_member": customer.is_member if customer else False,
                "member_rank": customer.member_rank if customer else None,
                "visit_count": customer.visit_count if customer else 0,
            } if customer else None,
            restriction=None,
        ).model_dump(mode="json")
    }
