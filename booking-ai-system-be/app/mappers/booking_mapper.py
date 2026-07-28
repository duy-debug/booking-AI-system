from datetime import time

from app.db.models.booking import Booking
from app.db.models.reservation import Reservation
from app.schemas.booking import PublicBookingResponse, ReservationResponse


# Chuẩn hóa time hoặc chuỗi giờ thành HH:MM để DTO không phụ thuộc cách SQLAlchemy biểu diễn dữ liệu.
def to_hhmm(value: object) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value)


# Chuyển ORM reservation thành Pydantic DTO, bao gồm course snapshot nằm ở relationship reservation_courses.
def reservation_to_response(reservation: Reservation) -> ReservationResponse:
    return ReservationResponse.model_validate({
        "reservation_id": reservation.reservation_id,
        "person_index": reservation.person_index,
        "therapist_id": reservation.therapist_id,
        "therapist_name": reservation.therapist.name,
        "start_time": reservation.start_time,
        "end_time": reservation.end_time,
        "status": reservation.status,
        "assignment_source": getattr(reservation, "assignment_source", "auto"),
        "courses": [
            {
                "course_id": course.course_id,
                "course_role": course.course_role,
                "course_name_snapshot": course.course_name_snapshot,
                "duration_snapshot": course.duration_snapshot,
                "price_snapshot": course.price_snapshot,
            }
            for course in reservation.reservation_courses
        ],
    })


# Chuyển ORM booking đã eager-load thành DTO public ổn định, không để model SQLAlchemy đi ra API layer.
def booking_to_public_response(booking: Booking) -> PublicBookingResponse:
    return PublicBookingResponse.model_validate({
        "booking_id": booking.booking_id,
        "shop_id": booking.shop_id,
        "shop_name": booking.shop.name,
        "customer_id": booking.customer_id,
        "booking_date": booking.booking_date,
        "start_time": booking.start_time,
        "end_time": booking.end_time,
        "number_of_people": booking.number_of_people,
        "total_duration_minutes": booking.total_duration_minutes,
        "status": booking.status,
        "therapist_request_type": booking.therapist_request_type,
        "requested_therapist_id": booking.requested_therapist_id,
        "requested_gender": booking.requested_gender,
        "cancel_reason": booking.cancel_reason,
        "cancelled_at": booking.cancelled_at,
        "created_at": booking.created_at,
        "updated_at": booking.updated_at,
        "reservations": [
            reservation_to_response(reservation)
            for reservation in booking.reservations
        ],
    })


# Chuyển DTO booking thành dictionary JSON-compatible cho các command service đang giữ contract cũ.
def booking_to_detail(booking: Booking) -> dict:
    return booking_to_public_response(booking).model_dump(mode="json")
