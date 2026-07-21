from datetime import date
from uuid import UUID

# Service tra cứu lịch làm việc của therapist — shift + reservation theo ngày
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.repositories import TherapistRepository, ShiftRepository, ReservationRepository


class TherapistBookingService:
    # Khởi tạo với session và repository
    def __init__(self, session: Session):
        self.session = session
        self.therapist_repo = TherapistRepository(session)
        self.shift_repo = ShiftRepository(session)
        self.reservation_repo = ReservationRepository(session)

    # Lịch làm việc của therapist theo ngày — gồm shift và danh sách reservation kèm course
    def get_schedule(self, therapist_id: UUID, schedule_date: date) -> dict:
        therapist = self.therapist_repo.find_by_id(therapist_id)
        if not therapist:
            raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Khong tim thay therapist")

        shift = self.shift_repo.find_by_therapist_and_date(therapist_id, schedule_date)
        reservations = self.reservation_repo.find_by_therapist_and_date(therapist_id, schedule_date)

        res_list = []
        for res in reservations:
            courses = self.reservation_repo.find_courses_by_reservation(res.reservation_id)
            res_list.append({
                "reservation_id": str(res.reservation_id),
                "booking_id": str(res.booking_id),
                "start_time": res.start_time.isoformat(),
                "end_time": res.end_time.isoformat(),
                "course_names": [c.course_name_snapshot for c in courses],
                "booking_status": res.booking.status if res.booking else None,
            })

        return {
            "therapist_id": str(therapist.therapist_id),
            "date": schedule_date.isoformat(),
            "shift": {
                "start_time": shift.start_time.isoformat() if shift else None,
                "end_time": shift.end_time.isoformat() if shift else None,
            } if shift else None,
            "reservations": res_list,
        }
