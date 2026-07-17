from datetime import date

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from app.core.auth import get_current_admin
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.schemas.therapist_shift import ShiftCreate, ShiftResponse, ShiftUpdate
from app.services.therapist_shift_service import TherapistShiftService

router = APIRouter(prefix="/api/admin", tags=["admin-shifts"], dependencies=[Depends(get_current_admin)])


# Danh sách ca làm việc trong shop — lọc theo ngày, therapist, trạng thái
@router.get("/shops/{shop_id}/therapist-shifts")
def list_shifts(
    shop_id: str,
    work_date: str | None = Query(None),
    therapist_id: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    uid = parse_uuid(shop_id, "shop")

    parsed_date: date | None = None
    if work_date is not None:
        try:
            parsed_date = date.fromisoformat(work_date)
        except ValueError:
            raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="work_date không đúng format YYYY-MM-DD")

    parsed_tid: str | None = None
    if therapist_id is not None:
        parsed_tid = parse_uuid(therapist_id, "therapist")

    service = TherapistShiftService(db)
    shifts = service.list(uid, work_date=parsed_date, therapist_id=parsed_tid, is_active=is_active)
    return {"data": [ShiftResponse.model_validate(s).model_dump(mode="json") for s in shifts]}


# Tạo ca làm việc mới — kiểm tra therapist thuộc shop, không trùng giờ
@router.post("/therapist-shifts", status_code=201)
def create_shift(body: ShiftCreate, db: Session = Depends(get_db)):
    service = TherapistShiftService(db)
    shift = service.create(body)
    return {"data": ShiftResponse.model_validate(shift).model_dump(mode="json")}


# Chi tiết ca làm việc theo ID
@router.get("/therapist-shifts/{shift_id}")
def get_shift(shift_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(shift_id, "shift")
    service = TherapistShiftService(db)
    shift = service.get(uid)
    return {"data": ShiftResponse.model_validate(shift).model_dump(mode="json")}


# Cập nhật ca làm việc — kiểm tra overlap khi thay đổi giờ
@router.patch("/therapist-shifts/{shift_id}")
def update_shift(shift_id: str, body: ShiftUpdate, db: Session = Depends(get_db)):
    uid = parse_uuid(shift_id, "shift")
    service = TherapistShiftService(db)
    shift = service.update(uid, body)
    return {"data": ShiftResponse.model_validate(shift).model_dump(mode="json")}
