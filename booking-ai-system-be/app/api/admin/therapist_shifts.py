# Admin CRUD — TherapistShifts (ca làm việc của therapist)

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.api.schemas.therapist_shift import ShiftCreate, ShiftResponse, ShiftUpdate
from app.db.models.shop import Shop
from app.db.models.therapist import Therapist
from app.db.models.therapist_shift import TherapistShift

router = APIRouter(prefix="/api/admin", tags=["admin-shifts"])


@router.get("/shops/{shop_id}/therapist-shifts")
def list_shifts(
    shop_id: str,
    work_date: str | None = Query(None),
    therapist_id: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách ca làm việc của shop — filter theo work_date, therapist_id, is_active
    uid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, uid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")

    stmt = select(TherapistShift).where(TherapistShift.shop_id == uid)
    if work_date is not None:
        from datetime import date
        try:
            d = date.fromisoformat(work_date)
        except ValueError:
            raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="work_date không đúng format YYYY-MM-DD")
        stmt = stmt.where(TherapistShift.work_date == d)
    if therapist_id is not None:
        tid = parse_uuid(therapist_id, "therapist")
        stmt = stmt.where(TherapistShift.therapist_id == tid)
    if is_active is not None:
        stmt = stmt.where(TherapistShift.is_active == is_active)
    shifts = db.scalars(stmt.order_by(TherapistShift.work_date, TherapistShift.start_time)).all()
    return {"data": [ShiftResponse.model_validate(s).model_dump(mode="json") for s in shifts]}


@router.post("/therapist-shifts", status_code=201)
def create_shift(body: ShiftCreate, db: Session = Depends(get_db)):
    # Tạo ca làm việc mới
    # Check shop tồn tại
    shop = db.get(Shop, body.shop_id)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
    # Check therapist tồn tại và thuộc shop
    therapist = db.get(Therapist, body.therapist_id)
    if not therapist:
        raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Không tìm thấy therapist")
    if therapist.shop_id != body.shop_id:
        raise AppError(400, code="THERAPIST_NOT_FOUND", detail="Therapist không thuộc shop này")

    # Check thời gian hợp lệ
    if body.start_time >= body.end_time:
        raise AppError(422, code="INVALID_SHIFT_TIME_RANGE", detail="end_time phải lớn hơn start_time")

    # Check trùng ca
    exist = db.scalar(
        select(TherapistShift).where(
            TherapistShift.therapist_id == body.therapist_id,
            TherapistShift.work_date == body.work_date,
            TherapistShift.start_time == body.start_time,
            TherapistShift.end_time == body.end_time,
            TherapistShift.is_active == True,
        )
    )
    if exist:
        raise AppError(409, code="SHIFT_TIME_CONFLICT", detail="Ca làm việc bị trùng với ca đã tồn tại")

    shift = TherapistShift(**body.model_dump())
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return {"data": ShiftResponse.model_validate(shift).model_dump(mode="json")}


@router.get("/therapist-shifts/{shift_id}")
def get_shift(shift_id: str, db: Session = Depends(get_db)):
    # Chi tiết ca làm việc
    uid = parse_uuid(shift_id, "shift")
    shift = db.get(TherapistShift, uid)
    if not shift:
        raise AppError(404, code="SHIFT_NOT_FOUND", detail="Không tìm thấy ca làm việc")
    return {"data": ShiftResponse.model_validate(shift).model_dump(mode="json")}


@router.patch("/therapist-shifts/{shift_id}")
def update_shift(shift_id: str, body: ShiftUpdate, db: Session = Depends(get_db)):
    # Cập nhật ca làm việc (partial update)
    uid = parse_uuid(shift_id, "shift")
    shift = db.get(TherapistShift, uid)
    if not shift:
        raise AppError(404, code="SHIFT_NOT_FOUND", detail="Không tìm thấy ca làm việc")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(shift, field, value)
    db.commit()
    db.refresh(shift)
    return {"data": ShiftResponse.model_validate(shift).model_dump(mode="json")}
