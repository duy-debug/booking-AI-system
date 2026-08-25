from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.mappers.booking_mapper import booking_to_public_response


def test_public_booking_mapper_includes_shop_and_therapist_names() -> None:
    course = SimpleNamespace(
        course_id=uuid4(),
        course_role="main",
        course_name_snapshot="Massage thư giãn toàn thân",
        duration_snapshot=60,
        price_snapshot=Decimal(450000),
    )
    reservation = SimpleNamespace(
        reservation_id=uuid4(),
        person_index=1,
        therapist_id=uuid4(),
        therapist=SimpleNamespace(name="Nguyễn Ngọc Anh"),
        start_time=time(10, 0),
        end_time=time(11, 0),
        status="assigned",
        assignment_source="auto",
        reservation_courses=[course],
    )
    now = datetime.now(UTC)
    booking = SimpleNamespace(
        booking_id=uuid4(),
        pos_booking_code="KMB-20260720-ABCDEFGH",
        shop_id=uuid4(),
        shop=SimpleNamespace(name="Komorebi Quận 1"),
        customer_id=uuid4(),
        customer=SimpleNamespace(phone="0901234567", name="Nguyen An"),
        booking_date=date(2026, 7, 20),
        start_time=time(10, 0),
        end_time=time(11, 0),
        number_of_people=1,
        total_duration_minutes=60,
        status="confirmed",
        therapist_request_type="none",
        requested_therapist_id=None,
        requested_gender=None,
        cancel_reason=None,
        cancelled_at=None,
        created_at=now,
        updated_at=now,
        reservations=[reservation],
    )

    result = booking_to_public_response(booking)

    assert result.shop_name == "Komorebi Quận 1"
    assert result.booking_code == "KMB-20260720-ABCDEFGH"
    assert result.customer_phone == "0901234567"
    assert result.customer_name == "Nguyen An"
    assert result.reservations[0].therapist_name == "Nguyễn Ngọc Anh"
