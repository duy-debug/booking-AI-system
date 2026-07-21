from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import AppError
from app.services import TherapistBookingService


router = APIRouter(prefix="/api/therapists", tags=["therapist"])


# Lịch làm việc của therapist theo ngày — ca làm việc + booking đã nhận
@router.get("/me/schedule")
def get_my_schedule(
    date_param: str = Query(..., alias="date"),
    therapist_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    try:
        d = date.fromisoformat(date_param)
    except ValueError:
        raise AppError(400, code="INVALID_DATE", detail="date khong dung format YYYY-MM-DD")

    if not therapist_id:
        raise AppError(400, code="INVALID_THERAPIST_ID", detail="Can therapist_id (tam thoi)")

    try:
        uid = UUID(therapist_id)
    except ValueError:
        raise AppError(400, code="INVALID_THERAPIST_ID", detail="therapist_id khong dung format UUID")

    service = TherapistBookingService(db)
    result = service.get_schedule(uid, d)
    return {"data": result}
