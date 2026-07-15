# Public — Booking CRUD (tạo, xem, sửa, hủy booking)
# POS integration: gọi POS để đồng bộ booking code và availability

import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Query
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, parse_uuid
from app.api.schemas.booking import (
    BookingCreate,
    BookingListItem,
    BookingPatchInput,
    ReservationCourseResponse,
    ReservationResponse,
)
from app.api.schemas.customer import CustomerBrief
from app.db.models.booking import Booking
from app.db.models.course import Course
from app.db.models.customer import Customer
from app.db.models.customer_restriction import CustomerRestriction
from app.db.models.reservation import Reservation
from app.db.models.reservation_course import ReservationCourse
from app.db.models.shop import Shop
from app.db.models.therapist import Therapist
from app.integrations.pos import get_pos_client
from app.integrations.pos.base import POSBookingData

router = APIRouter(prefix="/api/bookings", tags=["public-booking"])


@router.post("", status_code=201)
def create_booking(
    body: BookingCreate,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    # Tạo booking mới — cần Idempotency-Key header để tránh trùng
    # Check idempotency key
    if not idempotency_key:
        raise AppError(400, code="MISSING_IDEMPOTENCY_KEY", detail="Thiếu Idempotency-Key header")
    try:
        ik = uuid.UUID(idempotency_key)
    except ValueError:
        raise AppError(400, code="MISSING_IDEMPOTENCY_KEY", detail="Idempotency-Key không đúng format UUID")

    exist = db.scalar(select(Booking).where(Booking.idempotency_key == ik))
    if exist:
        raise AppError(409, code="SLOT_CONFLICT", detail="Idempotency-Key đã tồn tại")

    # Check shop
    shop = db.get(Shop, body.shop_id)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
    if not shop.is_active:
        raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

    # Check NG list
    restriction = db.scalar(
        select(CustomerRestriction).where(
            CustomerRestriction.phone == body.customer.phone,
            CustomerRestriction.is_active == True,
        )
    )
    if restriction:
        raise AppError(403, code="CUSTOMER_IN_NG_LIST", detail="Số điện thoại không được phép đặt booking")

    # Validate courses
    total_duration = 0
    has_main = False
    course_ids = [c.course_id for c in body.courses]
    db_courses = db.scalars(select(Course).where(Course.course_id.in_(course_ids), Course.shop_id == body.shop_id)).all()
    db_course_map = {c.course_id: c for c in db_courses}
    for c in body.courses:
        course = db_course_map.get(c.course_id)
        if not course:
            raise AppError(404, code="COURSE_NOT_FOUND", detail=f"Không tìm thấy course {c.course_id}")
        if c.course_role == "main":
            if has_main:
                raise AppError(422, code="INVALID_COURSE_COMBO", detail="Chỉ được chọn 1 main course")
            has_main = True
            if course.course_type != "main":
                raise AppError(422, code="INVALID_COURSE_COMBO", detail=f"Course {c.course_id} không phải main type")
        elif c.course_role == "addon":
            if course.course_type != "addon":
                raise AppError(422, code="INVALID_COURSE_COMBO", detail=f"Course {c.course_id} không phải addon type")
        total_duration += course.duration_minutes

    if not has_main:
        raise AppError(422, code="ADDON_REQUIRES_MAIN_COURSE", detail="Cần ít nhất 1 main course")

    # Validate therapist request
    therapist_request = body.therapist_request
    if therapist_request:
        if body.number_of_people > 1 and therapist_request.type != "none":
            raise AppError(422, code="GROUP_BOOKING_CANNOT_REQUEST_THERAPIST", detail="Booking nhóm không được yêu cầu therapist")

        requested_therapist_id = None
        requested_gender = None
        if therapist_request.type == "specific":
            if not therapist_request.therapist_id:
                raise AppError(422, code="INVALID_THERAPIST_DATA", detail="Cần therapist_id khi type = specific")
            therapist = db.get(Therapist, therapist_request.therapist_id)
            if not therapist or therapist.shop_id != body.shop_id:
                raise AppError(404, code="THERAPIST_NOT_FOUND", detail="Không tìm thấy therapist")
            requested_therapist_id = therapist.therapist_id
            requested_gender = therapist.gender
        elif therapist_request.type == "gender":
            if not therapist_request.gender:
                raise AppError(422, code="INVALID_THERAPIST_DATA", detail="Cần gender khi type = gender")
            requested_gender = therapist_request.gender
    else:
        therapist_request = None

    therapist_request_type = therapist_request.type if therapist_request else "none"

    # Calculate end_time
    start_dt = datetime.combine(body.booking_date, body.start_time)
    end_dt = start_dt + timedelta(minutes=total_duration)
    end_time = end_dt.time()

    # Check slot conflict (simple check)
    existing = db.scalar(
        select(Reservation)
        .join(Booking)
        .where(
            Booking.shop_id == body.shop_id,
            Booking.booking_date == body.booking_date,
            Booking.status != "cancelled",
            Reservation.start_time < end_time,
            Reservation.end_time > body.start_time,
        )
    )
    if existing:
        raise AppError(409, code="SLOT_CONFLICT", detail="Slot đã có người đặt")

    # Get or create customer
    customer = db.scalar(select(Customer).where(Customer.phone == body.customer.phone))
    if not customer:
        customer = Customer(
            phone=body.customer.phone,
            name=body.customer.name,
        )
        db.add(customer)
        db.flush()
    else:
        if body.customer.name:
            customer.name = body.customer.name

    # Create booking
    booking = Booking(
        shop_id=body.shop_id,
        customer_id=customer.customer_id,
        booking_date=body.booking_date,
        start_time=body.start_time,
        end_time=end_time,
        number_of_people=body.number_of_people,
        total_duration_minutes=total_duration,
        status="confirmed",
        therapist_request_type=therapist_request_type,
        requested_therapist_id=requested_therapist_id if therapist_request_type == "specific" else None,
        requested_gender=requested_gender if therapist_request_type in ("specific", "gender") else None,
        idempotency_key=ik,
    )
    db.add(booking)
    db.flush()

    # Create reservations
    assigned_therapist_ids: list[uuid.UUID] = []

    if body.number_of_people == 1:
        # Single person: 1 reservation
        res_therapist_id = None
        if therapist_request_type == "specific" and requested_therapist_id:
            res_therapist_id = requested_therapist_id
        else:
            # Assign first available therapist (simplified)
            therapist_stmt = select(Therapist).where(
                Therapist.shop_id == body.shop_id,
                Therapist.is_active == True,
            )
            first_therapist = db.scalars(therapist_stmt.limit(1)).first()
            res_therapist_id = first_therapist.therapist_id if first_therapist else None

        if not res_therapist_id:
            raise AppError(422, code="THERAPIST_NOT_AVAILABLE", detail="Không có therapist khả dụng")

        assigned_therapist_ids.append(res_therapist_id)

        reservation = Reservation(
            booking_id=booking.booking_id,
            person_index=1,
            therapist_id=res_therapist_id,
            start_time=body.start_time,
            end_time=end_time,
            status="assigned",
        )
        db.add(reservation)
        db.flush()

        # Create reservation_courses (snapshot)
        for c in body.courses:
            course = db_course_map[c.course_id]
            rc = ReservationCourse(
                reservation_id=reservation.reservation_id,
                course_id=c.course_id,
                course_role=c.course_role,
                duration_snapshot=course.duration_minutes,
                price_snapshot=course.price,
                course_name_snapshot=course.name,
            )
            db.add(rc)
    else:
        # Group booking: create N reservations, assign different therapists
        available_therapists = db.scalars(
            select(Therapist).where(
                Therapist.shop_id == body.shop_id,
                Therapist.is_active == True,
            ).limit(body.number_of_people)
        ).all()
        if len(available_therapists) < body.number_of_people:
            raise AppError(422, code="THERAPIST_NOT_AVAILABLE", detail="Không đủ therapist cho booking nhóm")

        # Calculate individual duration per person
        person_duration = total_duration
        person_end_dt = start_dt + timedelta(minutes=person_duration)
        person_end_time = person_end_dt.time()

        for i in range(body.number_of_people):
            tid = available_therapists[i].therapist_id
            assigned_therapist_ids.append(tid)

            res = Reservation(
                booking_id=booking.booking_id,
                person_index=i + 1,
                therapist_id=tid,
                start_time=body.start_time,
                end_time=person_end_time,
                status="assigned",
            )
            db.add(res)
            db.flush()

            for c in body.courses:
                course = db_course_map[c.course_id]
                rc = ReservationCourse(
                    reservation_id=res.reservation_id,
                    course_id=c.course_id,
                    course_role=c.course_role,
                    duration_snapshot=course.duration_minutes,
                    price_snapshot=course.price,
                    course_name_snapshot=course.name,
                )
                db.add(rc)

    # ===== POS Integration: đồng bộ booking code từ POS =====
    pos = get_pos_client()
    pos_shop = db.get(Shop, body.shop_id)
    pos_shop_code = pos_shop.pos_shop_code if pos_shop else ""

    # Chuẩn bị dữ liệu course cho POS
    pos_courses = []
    for c in body.courses:
        course = db_course_map.get(c.course_id)
        if course:
            pos_courses.append({
                "pos_course_code": course.pos_course_code,
                "course_role": c.course_role,
                "duration": course.duration_minutes,
                "price": course.price,
            })

    # Gửi booking lên POS
    pos_result = pos.create_booking(POSBookingData(
        pos_shop_code=pos_shop_code,
        booking_date=body.booking_date,
        start_time=body.start_time,
        end_time=end_time,
        number_of_people=body.number_of_people,
        total_duration_minutes=total_duration,
        customer_phone=body.customer.phone,
        customer_name=body.customer.name,
        courses=pos_courses,
        therapist_ids=assigned_therapist_ids if assigned_therapist_ids else None,
    ))

    if pos_result.success and pos_result.pos_booking_code:
        # POS xác nhận thành công → lưu mã
        booking.pos_booking_code = pos_result.pos_booking_code
        booking.pos_sync_status = "synced"
    elif not pos_result.success:
        # POS thất bại → vẫn tạo booking local, đánh dấu sync failed
        booking.pos_sync_status = "failed"
        # Không raise lỗi — booking vẫn tồn tại local, có thể retry sau
    else:
        booking.pos_sync_status = "pending"

    db.commit()
    db.refresh(booking)

    # Load response
    result = _load_booking_response(db, booking.booking_id)
    return {"data": result}


@router.get("")
def list_bookings(
    pos_booking_code: str | None = Query(None),
    phone: str | None = Query(None),
    shop_id: str | None = Query(None),
    booking_date: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    db: Session = Depends(get_db),
):
    # Danh sách booking — filter và cursor pagination
    stmt = select(Booking)
    if pos_booking_code:
        stmt = stmt.where(Booking.pos_booking_code == pos_booking_code)
    if phone:
        stmt = stmt.join(Customer).where(Customer.phone == phone)
    if shop_id:
        suid = parse_uuid(shop_id, "shop")
        stmt = stmt.where(Booking.shop_id == suid)
    if booking_date:
        try:
            bd = date.fromisoformat(booking_date)
            stmt = stmt.where(Booking.booking_date == bd)
        except ValueError:
            raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="booking_date không đúng format YYYY-MM-DD")
    if status:
        stmt = stmt.where(Booking.status == status)

    stmt = stmt.order_by(Booking.created_at.desc()).limit(limit + 1)
    bookings = db.scalars(stmt).all()

    has_more = len(bookings) > limit
    if has_more:
        bookings = bookings[:limit]

    return {
        "data": [BookingListItem.model_validate(b).model_dump(mode="json") for b in bookings],
        "meta": {
            "limit": limit,
            "next_cursor": str(bookings[-1].booking_id) if has_more else None,
        },
    }


@router.get("/{booking_id}")
def get_booking(booking_id: str, db: Session = Depends(get_db)):
    # Chi tiết booking — bao gồm reservations + course snapshots
    uid = parse_uuid(booking_id, "booking")
    booking = db.get(Booking, uid)
    if not booking:
        raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")
    result = _load_booking_response(db, uid)
    return {"data": result}


@router.patch("/{booking_id}")
def update_booking(booking_id: str, body: BookingPatchInput, db: Session = Depends(get_db)):
    # Cập nhật booking — nếu status=cancelled thì hủy booking
    uid = parse_uuid(booking_id, "booking")
    booking = db.get(Booking, uid)
    if not booking:
        raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")

    if body.status == "cancelled":
        # Cancel flow — đồng bộ với POS trước
        if booking.status == "cancelled":
            raise AppError(409, code="BOOKING_ALREADY_CANCELLED", detail="Booking đã bị hủy")

        # Thông báo huỷ cho POS (nếu booking đã synced)
        if booking.pos_booking_code:
            pos = get_pos_client()
            pos.cancel_booking(booking.pos_booking_code, reason=body.cancel_reason)

        booking.status = "cancelled"
        booking.pos_sync_status = "cancelled"
        booking.cancel_reason = body.cancel_reason
        booking.cancelled_at = datetime.now(timezone.utc)
    else:
        # Update flow — apply các field được gửi lên
        data = body.model_dump(exclude_unset=True, exclude_none=True)
        # Chỉ cho phép update các field thuộc DB model
        allowed_fields = {"booking_date", "start_time"}
        # courses / therapist_request là schema-only — cần logic riêng (chưa implement)
        for field, value in data.items():
            if field in allowed_fields:
                setattr(booking, field, value)

    db.commit()
    db.refresh(booking)
    result = _load_booking_response(db, uid)
    return {"data": result}


@router.get("/{booking_id}/reservations")
def list_reservations(booking_id: str, db: Session = Depends(get_db)):
    # Danh sách reservation của booking
    uid = parse_uuid(booking_id, "booking")
    booking = db.get(Booking, uid)
    if not booking:
        raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")

    reservations = db.scalars(
        select(Reservation)
        .where(Reservation.booking_id == uid)
        .order_by(Reservation.person_index)
    ).all()
    return {
        "data": [ReservationResponse.model_validate(r).model_dump(mode="json") for r in reservations],
    }


# ────────────── Helper ──────────────


def _load_booking_response(db: Session, booking_id: uuid.UUID) -> dict:
    # Load booking + reservations + course snapshots — trả về dict response
    booking = db.get(Booking, booking_id)
    if not booking:
        raise AppError(404, code="BOOKING_NOT_FOUND", detail="Không tìm thấy booking")

    # Lấy reservations kèm courses
    reservations = db.scalars(
        select(Reservation)
        .where(Reservation.booking_id == booking_id)
        .order_by(Reservation.person_index)
    ).all()

    res_list = []
    for res in reservations:
        courses = db.scalars(
            select(ReservationCourse)
            .where(ReservationCourse.reservation_id == res.reservation_id)
        ).all()
        res_list.append({
            "reservation_id": res.reservation_id,
            "person_index": res.person_index,
            "therapist_id": res.therapist_id,
            "start_time": res.start_time.isoformat(),
            "end_time": res.end_time.isoformat(),
            "status": res.status,
            "courses": [
                ReservationCourseResponse.model_validate(c).model_dump(mode="json")
                for c in courses
            ],
        })

    return {
        "booking_id": booking.booking_id,
        "pos_booking_code": booking.pos_booking_code,
        "pos_sync_status": booking.pos_sync_status,
        "shop_id": booking.shop_id,
        "customer_id": booking.customer_id,
        "booking_date": booking.booking_date.isoformat(),
        "start_time": booking.start_time.isoformat(),
        "end_time": booking.end_time.isoformat(),
        "number_of_people": booking.number_of_people,
        "total_duration_minutes": booking.total_duration_minutes,
        "status": booking.status,
        "therapist_request_type": booking.therapist_request_type,
        "requested_therapist_id": booking.requested_therapist_id,
        "requested_gender": booking.requested_gender,
        "cancel_reason": booking.cancel_reason,
        "cancelled_at": booking.cancelled_at.isoformat() if booking.cancelled_at else None,
        "created_at": booking.created_at.isoformat(),
        "updated_at": booking.updated_at.isoformat(),
        "reservations": res_list,
    }
