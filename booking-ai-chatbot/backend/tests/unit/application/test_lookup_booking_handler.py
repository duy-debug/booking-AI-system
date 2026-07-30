"""Tests for the booking lookup application handler."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.handlers.lookup_booking_handler import LookupBookingHandler
from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking, Customer, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import BookingNotFoundError

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")
ORIGINAL_BOOKING_ID = UUID("44444444-4444-4444-4444-444444444444")
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


class FakeBookingGateway:
    """Booking gateway fake that records booking lookups."""

    def __init__(
        self,
        booking: Booking,
        error: Exception | None = None,
    ) -> None:
        self.booking = booking
        self.error = error
        self.lookup_booking_call_count = 0
        self.received_booking_id: UUID | None = None

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        raise AssertionError("Unexpected search_shops call.")

    async def search_services(
        self,
        shop_id: UUID,
        query: str | None = None,
    ) -> list[Service]:
        raise AssertionError("Unexpected search_services call.")

    async def check_availability(
        self,
        shop_id: UUID,
        service_id: UUID,
        booking_date: date,
    ) -> list[time]:
        raise AssertionError("Unexpected check_availability call.")

    async def create_booking(
        self,
        shop_id: UUID,
        service_id: UUID,
        customer: Customer,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        raise AssertionError("Unexpected create_booking call.")

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        self.lookup_booking_call_count += 1
        self.received_booking_id = booking_id
        if self.error is not None:
            raise self.error
        return self.booking

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        raise AssertionError("Unexpected reschedule_booking call.")

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected cancel_booking call.")


def make_handler(fake: FakeBookingGateway) -> LookupBookingHandler:
    gateway: BookingGateway = fake
    return LookupBookingHandler(gateway)


def make_existing_context() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
        booking_id=ORIGINAL_BOOKING_ID,
        pending_action="lookup_booking",
    )


@pytest.mark.asyncio
async def test_execute_looks_up_and_returns_same_booking_without_context() -> None:
    fake = FakeBookingGateway(BOOKING)

    result = await make_handler(fake).execute(BOOKING_ID)

    assert fake.lookup_booking_call_count == 1
    assert fake.received_booking_id == BOOKING_ID
    assert result is BOOKING


@pytest.mark.asyncio
async def test_execute_updates_context_from_official_booking() -> None:
    context = make_existing_context()
    fake = FakeBookingGateway(BOOKING)

    result = await make_handler(fake).execute(BOOKING_ID, context)

    assert result is BOOKING
    assert context.booking_id == BOOKING_ID
    assert context.shop is SHOP
    assert context.service is SERVICE
    assert context.customer is CUSTOMER
    assert context.booking_date is BOOKING_DATE
    assert context.start_time is START_TIME
    assert context.state is BookingState.COMPLETED
    assert context.pending_action is None


@pytest.mark.asyncio
async def test_not_found_error_propagates_without_changing_context() -> None:
    error = BookingNotFoundError("Booking was not found.")
    context = make_existing_context()
    original_values = (
        context.booking_id,
        context.shop,
        context.service,
        context.customer,
        context.booking_date,
        context.start_time,
        context.state,
        context.pending_action,
    )
    fake = FakeBookingGateway(BOOKING, error=error)

    with pytest.raises(BookingNotFoundError) as exc_info:
        await make_handler(fake).execute(BOOKING_ID, context)

    assert exc_info.value is error
    assert fake.lookup_booking_call_count == 1
    assert (
        context.booking_id,
        context.shop,
        context.service,
        context.customer,
        context.booking_date,
        context.start_time,
        context.state,
        context.pending_action,
    ) == original_values
