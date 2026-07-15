# Admin CRUD — CustomerRestrictions (NG list — số điện thoại bị cấm)

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.api.schemas.customer_restriction import (
    RestrictionCreate,
    RestrictionResponse,
    RestrictionUpdate,
)
from app.db.models.customer_restriction import CustomerRestriction

router = APIRouter(prefix="/api/admin/customer-restrictions", tags=["admin-restrictions"])


@router.get("")
def list_restrictions(
    phone: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách restriction — filter theo phone, is_active
    stmt = select(CustomerRestriction)
    if phone is not None:
        stmt = stmt.where(CustomerRestriction.phone == phone)
    if is_active is not None:
        stmt = stmt.where(CustomerRestriction.is_active == is_active)
    restrictions = db.scalars(stmt.order_by(CustomerRestriction.created_at.desc())).all()
    return {
        "data": [RestrictionResponse.model_validate(r).model_dump(mode="json") for r in restrictions],
        "meta": {"total": len(restrictions)},
    }


@router.post("", status_code=201)
def create_restriction(body: RestrictionCreate, db: Session = Depends(get_db)):
    # Tạo restriction mới
    # Check đã có restriction active cho phone này chưa
    exist = db.scalar(
        select(CustomerRestriction).where(
            CustomerRestriction.phone == body.phone,
            CustomerRestriction.is_active == True,
        )
    )
    if exist:
        raise AppError(409, code="CUSTOMER_RESTRICTION_ALREADY_EXISTS", detail="Phone đã có restriction còn hiệu lực")

    restriction = CustomerRestriction(**body.model_dump())
    db.add(restriction)
    db.commit()
    db.refresh(restriction)
    return {"data": RestrictionResponse.model_validate(restriction).model_dump(mode="json")}


@router.get("/{restriction_id}")
def get_restriction(restriction_id: str, db: Session = Depends(get_db)):
    # Chi tiết restriction
    uid = parse_uuid(restriction_id, "restriction")
    restriction = db.get(CustomerRestriction, uid)
    if not restriction:
        raise AppError(404, code="CUSTOMER_RESTRICTION_NOT_FOUND", detail="Không tìm thấy restriction")
    return {"data": RestrictionResponse.model_validate(restriction).model_dump(mode="json")}


@router.patch("/{restriction_id}")
def update_restriction(restriction_id: str, body: RestrictionUpdate, db: Session = Depends(get_db)):
    # Cập nhật restriction (partial update)
    uid = parse_uuid(restriction_id, "restriction")
    restriction = db.get(CustomerRestriction, uid)
    if not restriction:
        raise AppError(404, code="CUSTOMER_RESTRICTION_NOT_FOUND", detail="Không tìm thấy restriction")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(restriction, field, value)
    db.commit()
    db.refresh(restriction)
    return {"data": RestrictionResponse.model_validate(restriction).model_dump(mode="json")}
