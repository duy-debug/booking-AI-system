from datetime import date, time

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.services import SlotService

router = APIRouter(prefix="/api/shops/{shop_id}", tags=["public-slots"])


# Tra cứu khung giờ trống — nhận số người, course chính/phụ, yêu cầu therapist
@router.get("/available-slots")
def list_available_slots(
    shop_id: str,
    booking_date: str = Query(...),
    number_of_people: int = Query(..., ge=1, le=3),
    main_course_id: str = Query(...),
    addon_course_ids: str | None = Query(None),
    therapist_request_type: str | None = Query(None, pattern=r"^(none|specific|gender)$"),
    therapist_id: str | None = Query(None),
    therapist_gender: str | None = Query(None, pattern=r"^(male|female)$"),
    db: Session = Depends(get_db),
):
    try:
        bdate = date.fromisoformat(booking_date)
    except ValueError:
        raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="booking_date không đúng format YYYY-MM-DD")

    suid = parse_uuid(shop_id, "shop")
    mcid = parse_uuid(main_course_id, "course")

    service = SlotService(db)
    return service.list_available_slots(
        shop_id=suid,
        booking_date=bdate,
        number_of_people=number_of_people,
        main_course_id=mcid,
        addon_course_ids=addon_course_ids,
        therapist_request_type=therapist_request_type,
        therapist_id=therapist_id,
        therapist_gender=therapist_gender,
    )


# Tra cứu therapist còn trống trong khung giờ — lọc theo giới tính
@router.get("/available-therapists")
def list_available_therapists(
    shop_id: str,
    booking_date: str = Query(...),
    start_time: str = Query(...),
    end_time: str = Query(...),
    gender: str | None = Query(None, pattern=r"^(male|female|any)$"),
    db: Session = Depends(get_db),
):
    try:
        bdate = date.fromisoformat(booking_date)
    except ValueError:
        raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="booking_date không đúng format YYYY-MM-DD")

    try:
        st = time.fromisoformat(start_time)
        et = time.fromisoformat(end_time)
    except ValueError:
        raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="start_time/end_time không đúng format HH:MM")

    suid = parse_uuid(shop_id, "shop")

    service = SlotService(db)
    return service.list_available_therapists(
        shop_id=suid,
        booking_date=bdate,
        start_time=st,
        end_time=et,
        gender=gender,
    )
