# Admin — Booking monitoring (danh sách + detail — nhiều field hơn public)

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, parse_uuid
from app.core.exceptions import AppError
from app.db.models.booking import Booking
from app.db.models.customer import Customer
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.db.models.shop import Shop

router = APIRouter(prefix="/api/admin/bookings", tags=["admin-bookings"])


@router.get("")
def list_admin_bookings(
    shop_id: str | None = Query(None),
    booking_date: str | None = Query(None),
    status: str | None = Query(None),
    phone: str | None = Query(None),
    pos_booking_code: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách booking cho admin — kèm customer info
    stmt = select(Booking).options(joinedload(Booking.customer))

    if shop_id:
        suid = parse_uuid(shop_id, "shop")
        stmt = stmt.where(Booking.shop_id == suid)
    if booking_date:
        try:
            bd = date.fromisoformat(booking_date)
            stmt = stmt.where(Booking.booking_date == bd)
        except ValueError:
            raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="booking_date khong dung format YYYY-MM-DD")
    if status:
        stmt = stmt.where(Booking.status == status)
    if phone:
        stmt = stmt.join(Customer).where(Customer.phone == phone)
    if pos_booking_code:
        stmt = stmt.where(Booking.pos_booking_code == pos_booking_code)

    stmt = stmt.order_by(Booking.created_at.desc()).limit(limit + 1)
    bookings = db.scalars(stmt).unique().all()

    has_more = len(bookings) > limit
    if has_more:
        bookings = bookings[:limit]

    result = []
    for b in bookings:
        result.append({
            "booking_id": str(b.booking_id),
            "pos_booking_code": b.pos_booking_code,
            "shop_id": str(b.shop_id),
            "customer": {
                "customer_id": str(b.customer.customer_id),
                "phone": b.customer.phone,
                "name": b.customer.name,
            } if b.customer else None,
            "booking_date": b.booking_date.isoformat(),
            "start_time": b.start_time.isoformat(),
            "end_time": b.end_time.isoformat(),
            "number_of_people": b.number_of_people,
            "status": b.status,
        })

    return {
        "data": result,
        "meta": {
            "limit": limit,
            "next_cursor": str(bookings[-1].booking_id) if has_more else None,
        },
    }


@router.get("/{booking_id}")
def get_admin_booking(booking_id: str, db: Session = Depends(get_db)):
    # Chi tiết booking cho admin — kèm shop, customer, reservations, course snapshots
    uid = parse_uuid(booking_id, "booking")
    booking = db.get(Booking, uid)
    if not booking:
        raise AppError(404, code="BOOKING_NOT_FOUND", detail="Khong tim thay booking")

    # Shop
    shop = db.get(Shop, booking.shop_id)
    # Customer
    customer = db.get(Customer, booking.customer_id)
    # Reservations + courses
    reservations = db.scalars(
        select(Reservation)
        .where(Reservation.booking_id == uid)
        .order_by(Reservation.person_index)
    ).all()

    res_list = []
    for res in reservations:
        courses = db.scalars(
            select(ReservationCourse)
            .where(ReservationCourse.reservation_id == res.reservation_id)
        ).all()
        res_list.append({
            "reservation_id": str(res.reservation_id),
            "person_index": res.person_index,
            "therapist": {
                "therapist_id": str(res.therapist_id),
                "name": res.therapist.name if res.therapist else None,
            },
            "courses": [
                {
                    "course_role": c.course_role,
                    "course_name_snapshot": c.course_name_snapshot,
                    "duration_snapshot": c.duration_snapshot,
                    "price_snapshot": float(c.price_snapshot),
                }
                for c in courses
            ],
        })

    return {
        "data": {
            "booking_id": str(booking.booking_id),
            "pos_booking_code": booking.pos_booking_code,
            "status": booking.status,
            "shop": {
                "shop_id": str(shop.shop_id) if shop else None,
                "name": shop.name if shop else None,
            },
            "customer": {
                "customer_id": str(customer.customer_id) if customer else None,
                "phone": customer.phone if customer else None,
                "name": customer.name if customer else None,
                "is_member": customer.is_member if customer else False,
                "member_rank": customer.member_rank if customer else None,
                "visit_count": customer.visit_count if customer else 0,
            } if customer else None,
            "booking_date": booking.booking_date.isoformat(),
            "start_time": booking.start_time.isoformat(),
            "end_time": booking.end_time.isoformat(),
            "number_of_people": booking.number_of_people,
            "total_duration_minutes": booking.total_duration_minutes,
            "reservations": res_list,
        },
    }
