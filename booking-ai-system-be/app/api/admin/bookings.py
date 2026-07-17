from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, parse_uuid
from app.core.auth import get_current_admin
from app.core.exceptions import AppError
from app.repositories.booking_repository import BookingRepository
from app.repositories.shop_repository import ShopRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.reservation_repository import ReservationRepository

router = APIRouter(prefix="/api/admin/bookings", tags=["admin-bookings"], dependencies=[Depends(get_current_admin)])


# Danh sách booking (admin) — lọc theo shop, ngày, trạng thái, số điện thoại, mã POS
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
    suid = parse_uuid(shop_id, "shop") if shop_id else None
    bd = date.fromisoformat(booking_date) if booking_date else None

    booking_repo = BookingRepository(db)
    bookings = booking_repo.find_admin_all(
        shop_id=suid,
        booking_date=bd,
        status=status or None,
        phone=phone or None,
        pos_booking_code=pos_booking_code or None,
        limit=limit + 1,
    )

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


# Chi tiết booking (admin) — kèm thông tin khách hàng, shop, reservation, course
@router.get("/{booking_id}")
def get_admin_booking(booking_id: str, db: Session = Depends(get_db)):
    uid = parse_uuid(booking_id, "booking")
    booking_repo = BookingRepository(db)
    booking = booking_repo.find_by_id(uid)
    if not booking:
        raise AppError(404, code="BOOKING_NOT_FOUND", detail="Khong tim thay booking")

    shop_repo = ShopRepository(db)
    shop = shop_repo.find_by_id(booking.shop_id)

    customer_repo = CustomerRepository(db)
    customer = customer_repo.find_by_id(booking.customer_id)

    reservation_repo = ReservationRepository(db)
    reservations = reservation_repo.find_by_booking(uid)

    res_list = []
    for res in reservations:
        courses = reservation_repo.find_courses_by_reservation(res.reservation_id)
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
