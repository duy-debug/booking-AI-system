# Public — Available Slots & Available Therapists
# Slot là computed resource: tính từ shift - reservation đã có

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from app.core.exceptions import AppError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, parse_uuid
from app.api.schemas.available_slot import (
    AvailableSlotMeta,
    AvailableSlotResponse,
    AvailableTherapistResponse,
)
from app.db.models.course import Course
from app.db.models.reservation import Reservation
from app.db.models.shop import Shop
from app.db.models.therapist import Therapist
from app.db.models.therapist_shift import TherapistShift

router = APIRouter(prefix="/api/shops/{shop_id}", tags=["public-slots"])


def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _minutes_to_time(m: int) -> time:
    return time(m // 60, m % 60)


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
    # Tính toán slot khả dụng dựa trên shift therapist - booking đã có
    # Parse date
    try:
        bdate = date.fromisoformat(booking_date)
    except ValueError:
        raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="booking_date không đúng format YYYY-MM-DD")

    # Check shop
    suid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, suid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
    if not shop.is_active:
        raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

    # Check main course
    mcid = parse_uuid(main_course_id, "course")
    main_course = db.get(Course, mcid)
    if not main_course or main_course.shop_id != suid:
        raise AppError(404, code="COURSE_NOT_FOUND", detail="Không tìm thấy main course")
    if main_course.course_type != "main":
        raise AppError(422, code="INVALID_COURSE_COMBO", detail="main_course_id phải là course type 'main'")

    # Tính tổng duration (main + addon)
    total_duration = main_course.duration_minutes
    if addon_course_ids:
        for aid_str in addon_course_ids.split(","):
            aid_str = aid_str.strip()
            if not aid_str:
                continue
            aid = parse_uuid(aid_str, "course")
            addon = db.get(Course, aid)
            if not addon or addon.shop_id != suid:
                raise AppError(404, code="COURSE_NOT_FOUND", detail=f"Không tìm thấy addon course {aid_str}")
            if addon.course_type != "addon":
                raise AppError(422, code="INVALID_COURSE_COMBO", detail=f"{aid_str} không phải course type 'addon'")
            total_duration += addon.duration_minutes

    # Lấy therapist shifts active trong ngày
    stmt = (
        select(TherapistShift)
        .where(
            TherapistShift.shop_id == suid,
            TherapistShift.work_date == bdate,
            TherapistShift.is_active == True,
        )
        .options(joinedload(TherapistShift.therapist))
    )
    shifts = db.scalars(stmt).all()

    # Lọc therapist theo yêu cầu
    filtered_shifts = []
    for shift in shifts:
        t = shift.therapist
        if not t.is_active:
            continue
        if therapist_request_type == "specific" and therapist_id:
            if str(t.therapist_id) != therapist_id:
                continue
        if therapist_request_type == "gender" and therapist_gender:
            if t.gender != therapist_gender:
                continue
        filtered_shifts.append(shift)

    if not filtered_shifts:
        return {
            "data": [],
            "meta": AvailableSlotMeta(
                booking_date=bdate, shop_id=suid, number_of_people=number_of_people
            ).model_dump(mode="json"),
        }

    # Lấy reservation đã có trong ngày (confirmed bookings)
    from app.db.models.booking import Booking
    booked_intervals: list[tuple[int, int]] = []
    if number_of_people == 1:
        # Booking 1 người: check tất cả reservation trong ngày
        reservations = db.scalars(
            select(Reservation)
            .join(Booking)
            .where(
                Booking.shop_id == suid,
                Booking.booking_date == bdate,
                Booking.status != "cancelled",
            )
        ).all()
        for res in reservations:
            booked_intervals.append(
                (_time_to_minutes(res.start_time), _time_to_minutes(res.end_time))
            )
    else:
        # Booking nhóm: check toàn bộ booking — nếu có bất kỳ reservation nào overlap thì cả slot không available
        bookings = db.scalars(
            select(Booking)
            .where(
                Booking.shop_id == suid,
                Booking.booking_date == bdate,
                Booking.status != "cancelled",
            )
        ).all()
        for bk in bookings:
            booked_intervals.append(
                (_time_to_minutes(bk.start_time), _time_to_minutes(bk.end_time))
            )

    # Merge intervals
    if booked_intervals:
        booked_intervals.sort()
        merged = [booked_intervals[0]]
        for start, end in booked_intervals[1:]:
            if start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        booked_intervals = merged

    # Với booking nhóm, cần check có đủ therapist rảnh không
    if number_of_people > 1:
        needed_therapists = number_of_people
        available_therapist_count = len(filtered_shifts)
        if available_therapist_count < needed_therapists:
            return {
                "data": [],
                "meta": AvailableSlotMeta(
                    booking_date=bdate, shop_id=suid, number_of_people=number_of_people
                ).model_dump(mode="json"),
            }

    # Tạo free intervals cho mỗi shift, tìm intervals chung overlap với đủ therapist
    # Đơn giản hóa: dùng min_start..max_end của tất cả shift, check booking không overlap
    if not filtered_shifts:
        return {
            "data": [],
            "meta": AvailableSlotMeta(
                booking_date=bdate, shop_id=suid, number_of_people=number_of_people
            ).model_dump(mode="json"),
        }

    # Lấy khoảng giờ chung (intersection of all shift intervals)
    shift_intervals = [
        (_time_to_minutes(s.start_time), _time_to_minutes(s.end_time))
        for s in filtered_shifts
    ]
    common_start = max(s[0] for s in shift_intervals)
    common_end = min(s[1] for s in shift_intervals)

    if common_start >= common_end:
        return {
            "data": [],
            "meta": AvailableSlotMeta(
                booking_date=bdate, shop_id=suid, number_of_people=number_of_people
            ).model_dump(mode="json"),
        }

    # Cắt booked intervals khỏi common range
    free_intervals: list[tuple[int, int]] = [(common_start, common_end)]
    for b_start, b_end in booked_intervals:
        new_free = []
        for f_start, f_end in free_intervals:
            if b_end <= f_start or b_start >= f_end:
                new_free.append((f_start, f_end))
            else:
                if b_start > f_start:
                    new_free.append((f_start, b_start))
                if b_end < f_end:
                    new_free.append((b_end, f_end))
        free_intervals = new_free

    # Tạo slot từ free intervals (step = 15 phút)
    step = 15
    slots: list[dict] = []
    for f_start, f_end in free_intervals:
        cursor = f_start
        while cursor + total_duration <= f_end:
            slots.append(
                AvailableSlotResponse(
                    start_time=_minutes_to_time(cursor),
                    end_time=_minutes_to_time(cursor + total_duration),
                    duration_minutes=total_duration,
                    available=True,
                ).model_dump(mode="json")
            )
            cursor += step

    return {
        "data": slots,
        "meta": AvailableSlotMeta(
            booking_date=bdate, shop_id=suid, number_of_people=number_of_people
        ).model_dump(mode="json"),
    }


@router.get("/available-therapists")
def list_available_therapists(
    shop_id: str,
    booking_date: str = Query(...),
    start_time: str = Query(...),
    end_time: str = Query(...),
    gender: str | None = Query(None, pattern=r"^(male|female|any)$"),
    db: Session = Depends(get_db),
):
    # Danh sách therapist khả dụng trong khoảng thời gian
    try:
        bdate = date.fromisoformat(booking_date)
    except ValueError:
        raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="booking_date không đúng format YYYY-MM-DD")

    try:
        st = time.fromisoformat(start_time)
        et = time.fromisoformat(end_time)
    except ValueError:
        raise AppError(400, code="INVALID_QUERY_PARAMETER", detail="start_time/end_time không đúng format HH:MM")

    if st >= et:
        raise AppError(422, code="INVALID_TIME_RANGE", detail="end_time phải lớn hơn start_time")

    suid = parse_uuid(shop_id, "shop")
    shop = db.get(Shop, suid)
    if not shop:
        raise AppError(404, code="SHOP_NOT_FOUND", detail="Không tìm thấy shop")
    if not shop.is_active:
        raise AppError(422, code="SHOP_INACTIVE", detail="Shop không hoạt động")

    # Lấy therapist shifts active trong ngày
    stmt = (
        select(TherapistShift)
        .where(
            TherapistShift.shop_id == suid,
            TherapistShift.work_date == bdate,
            TherapistShift.is_active == True,
        )
        .options(joinedload(TherapistShift.therapist))
    )
    shifts = db.scalars(stmt).all()

    # Lọc shift covers requested time
    available_therapists = []
    for shift in shifts:
        t = shift.therapist
        if not t.is_active:
            continue
        if gender and gender != "any" and t.gender != gender:
            continue
        if shift.start_time <= st and shift.end_time >= et:
            # Check therapist không có reservation overlap
            from app.db.models.booking import Booking
            overlap = db.scalar(
                select(Reservation)
                .join(Booking)
                .where(
                    Reservation.therapist_id == t.therapist_id,
                    Booking.booking_date == bdate,
                    Booking.status != "cancelled",
                    Reservation.start_time < et,
                    Reservation.end_time > st,
                )
            )
            available_therapists.append(
                AvailableTherapistResponse(
                    therapist_id=t.therapist_id,
                    shop_id=suid,
                    name=t.name,
                    gender=t.gender,
                    available=(overlap is None),
                ).model_dump(mode="json")
            )

    return {"data": available_therapists}
