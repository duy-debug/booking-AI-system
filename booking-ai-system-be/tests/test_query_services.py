from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.booking import PublicBookingResponse
from app.schemas.schedule import ScheduleResponse
from app.services.booking_query_service import BookingQueryService
from app.services.schedule_service import ScheduleService


# Tạo booking giả đã có đầy đủ relationship để kiểm tra mapper mà không cần database ngoài.
def _booking():
    customer = SimpleNamespace(
        customer_id=uuid4(),
        phone="0900000000",
        name="Khách thử nghiệm",
    )
    therapist = SimpleNamespace(name="Nhân viên thử nghiệm")
    course = SimpleNamespace(
        course_id=uuid4(),
        course_role="main",
        course_name_snapshot="Massage",
        duration_snapshot=60,
        price_snapshot=Decimal("100.00"),
    )
    reservation = SimpleNamespace(
        reservation_id=uuid4(),
        person_index=1,
        therapist_id=uuid4(),
        therapist=therapist,
        start_time=time(10),
        end_time=time(11),
        status="assigned",
        assignment_source="auto",
        reservation_courses=[course],
    )
    now = datetime.now(UTC)
    shop = SimpleNamespace(shop_id=uuid4(), name="Shop test")
    return SimpleNamespace(
        booking_id=uuid4(),
        pos_booking_code=None,
        shop_id=shop.shop_id,
        shop=shop,
        customer_id=customer.customer_id,
        customer=customer,
        booking_date=date(2026, 7, 22),
        start_time=time(10),
        end_time=time(11),
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


# Xác nhận BookingQueryService trả Pydantic DTO thay vì làm lộ ORM model lên router.
def test_booking_query_service_returns_public_dto():
    booking = _booking()
    service = BookingQueryService.__new__(BookingQueryService)
    service.booking_repo = SimpleNamespace(find_by_id=lambda _booking_id: booking)

    response = service.get_public_detail(booking.booking_id)

    assert isinstance(response.data, PublicBookingResponse)
    assert response.data.booking_id == booking.booking_id
    assert response.data.customer_phone == booking.customer.phone
    assert response.data.customer_name == booking.customer.name
    assert response.data.reservations[0].courses[0].course_name_snapshot == "Massage"


# Xác nhận ScheduleService tổng hợp dữ liệu từ các repository chuyên trách thành schema timeline.
def test_schedule_service_returns_schedule_dto():
    booking = _booking()
    shop = SimpleNamespace(shop_id=booking.shop_id, name="Shop thử nghiệm")
    therapist = SimpleNamespace(
        therapist_id=booking.reservations[0].therapist_id,
        name="Nhân viên thử nghiệm",
        gender="female",
        is_active=True,
    )
    shift = SimpleNamespace(
        shift_id=uuid4(),
        therapist_id=therapist.therapist_id,
        therapist=therapist,
        start_time=time(9),
        end_time=time(18),
        is_active=True,
    )
    service = ScheduleService.__new__(ScheduleService)
    service.shop_repo = SimpleNamespace(find_by_id=lambda _shop_id: shop)
    service.therapist_repo = SimpleNamespace(find_by_shop=lambda _shop_id: [therapist])
    service.shift_repo = SimpleNamespace(
        find_by_shop=lambda _shop_id, work_date: [shift]
    )
    service.booking_repo = SimpleNamespace(
        find_bookings_with_reservations=lambda _shop_id, _date: [booking]
    )

    response = service.get_daily_schedule(booking.shop_id, booking.booking_date)

    assert isinstance(response.data, ScheduleResponse)
    assert response.data.shop.shop_id == booking.shop_id
    assert response.data.bookings[0].reservations[0].assignment_source == "auto"
