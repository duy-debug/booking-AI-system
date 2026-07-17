from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from app.core.auth import get_current_admin
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.schemas.therapist import TherapistCreate, TherapistResponse, TherapistUpdate
from app.services.therapist_service import TherapistService

router = APIRouter(prefix="/api/admin", tags=["admin-therapists"], dependencies=[Depends(get_current_admin)])


# Danh sách therapist trong shop — lọc theo trạng thái hoạt động
@router.get("/shops/{shop_id}/therapists")
def list_therapists(
    shop_id: str,
    is_active: bool | None = Query(None),
    db: Session = Depends(get_db),
):
    uid = parse_uuid(shop_id, "shop")
    service = TherapistService(db)
    therapists = service.list(uid, is_active=is_active)
    return {
        "data": [TherapistResponse.model_validate(t).model_dump(mode="json") for t in therapists],
    }


# Tạo therapist mới trong shop — pos_therapist_code phải duy nhất trong shop
@router.post("/shops/{shop_id}/therapists", status_code=201)
def create_therapist(shop_id: str, body: TherapistCreate, db: Session = Depends(get_db)):
    uid = parse_uuid(shop_id, "shop")
    service = TherapistService(db)
    therapist = service.create(uid, body)
    return {"data": TherapistResponse.model_validate(therapist).model_dump(mode="json")}


# Chi tiết therapist theo ID
@router.get("/therapists/{therapist_id}")
def get_therapist(therapist_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(therapist_id, "therapist")
    service = TherapistService(db)
    therapist = service.get(uid)
    return {"data": TherapistResponse.model_validate(therapist).model_dump(mode="json")}


# Cập nhật therapist — chỉ gửi các field cần thay đổi
@router.patch("/therapists/{therapist_id}")
def update_therapist(therapist_id: str, body: TherapistUpdate, db: Session = Depends(get_db)):
    uid = parse_uuid(therapist_id, "therapist")
    service = TherapistService(db)
    therapist = service.update(uid, body)
    return {"data": TherapistResponse.model_validate(therapist).model_dump(mode="json")}
