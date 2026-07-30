"""Tests for completing a booking conversation."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

from app.application.handlers.complete_booking_handler import CompleteBookingHandler
from app.domain.booking import Booking, Customer, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")
BOOKING_DATE = date(2026, 8, 1)
START_TIME = time(10, 30)
SHOP = Shop(shop_id=SHOP_ID, name="Central Spa")
SERVICE = Service(
    service_id=SERVICE_ID,
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)
CUSTOMER = Customer(phone="0901234567", name="Nguyen An")
BOOKING = Booking(
    booking_id=BOOKING_ID,
    status="confirmed",
    shop=SHOP,
    service=SERVICE,
    customer=CUSTOMER,
    booking_date=BOOKING_DATE,
    start_time=START_TIME,
)


def test_execute_returns_same_booking_and_synchronizes_context() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        pending_action="complete_booking",
    )

    result = CompleteBookingHandler().execute(context, BOOKING)

    assert result is BOOKING
    assert context.booking_id == BOOKING_ID
    assert context.shop is SHOP
    assert context.service is SERVICE
    assert context.customer is CUSTOMER
    assert context.booking_date is BOOKING_DATE
    assert context.start_time is START_TIME
    assert context.state is BookingState.COMPLETED
    assert context.pending_action is None


def test_execute_does_not_modify_official_booking() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
    )
    original_status = BOOKING.status

    result = CompleteBookingHandler().execute(context, BOOKING)

    assert result is BOOKING
    assert BOOKING.status == original_status
    assert BOOKING.status == "confirmed"
