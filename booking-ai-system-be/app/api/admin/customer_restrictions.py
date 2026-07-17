from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from app.core.auth import get_current_admin
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.schemas.customer_restriction import (
    RestrictionCreate,
    RestrictionResponse,
    RestrictionUpdate,
)
from app.services.restriction_service import RestrictionService

router = APIRouter(prefix="/api/admin/customer-restrictions", tags=["admin-restrictions"], dependencies=[Depends(get_current_admin)])


# Danh sách restriction — lọc theo số điện thoại và trạng thái
@router.get("")
def list_restrictions(
    phone: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    service = RestrictionService(db)
    restrictions = service.list(phone=phone, is_active=is_active)
    return {
        "data": [RestrictionResponse.model_validate(r).model_dump(mode="json") for r in restrictions],
        "meta": {"total": len(restrictions)},
    }


# Thêm restriction mới — không cho phép hai restriction active cho cùng số điện thoại
@router.post("", status_code=201)
def create_restriction(body: RestrictionCreate, db: Session = Depends(get_db)):
    service = RestrictionService(db)
    restriction = service.create(body)
    return {"data": RestrictionResponse.model_validate(restriction).model_dump(mode="json")}


# Chi tiết restriction theo ID
@router.get("/{restriction_id}")
def get_restriction(restriction_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(restriction_id, "restriction")
    service = RestrictionService(db)
    restriction = service.get(uid)
    return {"data": RestrictionResponse.model_validate(restriction).model_dump(mode="json")}


# Cập nhật restriction — khi reactivate, kiểm tra không trùng với restriction active khác
@router.patch("/{restriction_id}")
def update_restriction(restriction_id: str, body: RestrictionUpdate, db: Session = Depends(get_db)):
    uid = parse_uuid(restriction_id, "restriction")
    service = RestrictionService(db)
    restriction = service.update(uid, body)
    return {"data": RestrictionResponse.model_validate(restriction).model_dump(mode="json")}
