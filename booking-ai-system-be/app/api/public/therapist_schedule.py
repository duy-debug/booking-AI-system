# Therapist — Xem lịch làm việc
# TODO: cần auth middleware để lấy therapist_id từ token

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import AppError
from app.db.models.booking import Booking
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.db.models.therapist import Therapist
from app.db.models.therapist_shift import TherapistShift

router = APIRouter(prefix="/api/therapists", tags=["therapist"])


@router.get("/me/schedule")
def get_my_schedule(
    date_param: str = Query(..., alias="date"),
    therapist_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    # Lịch làm việc của therapist theo ngày
    # TODO: khi có auth, lấy therapist_id từ token — hiện tại dùng query param tạm
    try:
        d = date.fromisoformat(date_param)
    except ValueError:
        raise AppError(400, code="INVALID_DATE", detail="date khong dung format YYYY-MM-DD")

    if not therapist_id:
        raise AppError(400, code="INVALID_THERAPIST_ID", detail="Can therapist_id (tam thoi)")

    uid = None
    try:
        from uuid import UUID
        uid = UUID(therapist_id)
    except ValueError:
        raise AppError(400, code="INVALID_THERAPIST_ID", detail="therapist_id khong dung format UUID")

    therapist = db.get(Therapist, uid)
    if not therapist:
        raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Khong tim thay therapist")

    # Shift trong ngày
    shift = db.scalar(
        select(TherapistShift).where(
            TherapistShift.therapist_id == uid,
            TherapistShift.work_date == d,
            TherapistShift.is_active == True,
        )
    )

    # Reservations trong ngày (join qua Booking để lấy booking_date)
    reservations = db.scalars(
        select(Reservation)
        .join(Booking)
        .where(
            Reservation.therapist_id == uid,
            Booking.booking_date == d,
            Booking.status != "cancelled",
        )
        .order_by(Reservation.start_time)
    ).all()

    res_list = []
    for res in reservations:
        courses = db.scalars(
            select(ReservationCourse)
            .where(ReservationCourse.reservation_id == res.reservation_id)
        ).all()
        res_list.append({
            "reservation_id": str(res.reservation_id),
            "booking_id": str(res.booking_id),
            "start_time": res.start_time.isoformat(),
            "end_time": res.end_time.isoformat(),
            "course_names": [c.course_name_snapshot for c in courses],
            "booking_status": res.booking.status if res.booking else None,
        })

    return {
        "data": {
            "therapist_id": str(therapist.therapist_id),
            "date": date_param,
            "shift": {
                "start_time": shift.start_time.isoformat() if shift else None,
                "end_time": shift.end_time.isoformat() if shift else None,
            } if shift else None,
            "reservations": res_list,
        },
    }
