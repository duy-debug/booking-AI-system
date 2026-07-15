# Admin CRUD — Therapists (nhân viên massage) — nested dưới shop

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.api.schemas.therapist import TherapistCreate, TherapistResponse, TherapistUpdate
from app.db.models.shop import Shop
from app.db.models.therapist import Therapist

router = APIRouter(prefix="/api/admin", tags=["admin-therapists"])


@router.get("/shops/{shop_id}/therapists")
def list_therapists(
    shop_id: str,
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách therapist của shop — filter theo is_active
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

    stmt = select(Therapist).where(Therapist.shop_id == uid)
    if is_active is not None:
        stmt = stmt.where(Therapist.is_active == is_active)
    therapists = db.scalars(stmt.order_by(Therapist.name)).all()
    return {
        "data": [TherapistResponse.model_validate(t).model_dump(mode="json") for t in therapists],
    }


@router.post("/shops/{shop_id}/therapists", status_code=201)
def create_therapist(shop_id: str, body: TherapistCreate, db: Session = Depends(get_db)):
    # Tạo therapist mới cho shop
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

    # Check trùng pos_therapist_code trong shop
    exist = db.scalar(
        select(Therapist).where(Therapist.shop_id == uid, Therapist.pos_therapist_code == body.pos_therapist_code)
    )
    if exist:
        raise AppError(409, code="POS_THERAPIST_CODE_ALREADY_EXISTS", detail="pos_therapist_code đã tồn tại trong shop")

    therapist = Therapist(shop_id=uid, **body.model_dump())
    db.add(therapist)
    db.commit()
    db.refresh(therapist)
    return {"data": TherapistResponse.model_validate(therapist).model_dump(mode="json")}


@router.get("/therapists/{therapist_id}")
def get_therapist(therapist_id: str, db: Session = Depends(get_db)):
    # Chi tiết therapist
    uid = parse_uuid(therapist_id, "therapist")
    therapist = db.get(Therapist, uid)
    if not therapist:
        raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Không tìm thấy therapist")
    return {"data": TherapistResponse.model_validate(therapist).model_dump(mode="json")}


@router.patch("/therapists/{therapist_id}")
def update_therapist(therapist_id: str, body: TherapistUpdate, db: Session = Depends(get_db)):
    # Cập nhật therapist (partial update)
    uid = parse_uuid(therapist_id, "therapist")
    therapist = db.get(Therapist, uid)
    if not therapist:
        raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Không tìm thấy therapist")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(therapist, field, value)
    db.commit()
    db.refresh(therapist)
    return {"data": TherapistResponse.model_validate(therapist).model_dump(mode="json")}
