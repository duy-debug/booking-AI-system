"""Tests for the official booking creation handler."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking, Customer, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import (
    BookingConflictError,
    InvalidBookingDataError,
    InvalidBookingStateError,
)

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")
OLD_BOOKING_ID = UUID("44444444-4444-4444-4444-444444444444")
BOOKING_DATE = date(2099, 8, 1)
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
    """Booking gateway fake that records booking creation."""

    def __init__(
        self,
        booking: Booking,
        error: Exception | None = None,
    ) -> None:
        self.booking = booking
        self.error = error
        self.create_booking_call_count = 0
        self.received_shop_id: UUID | None = None
        self.received_service_id: UUID | None = None
        self.received_customer: Customer | None = None
        self.received_booking_date: date | None = None
        self.received_start_time: time | None = None

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
        self.create_booking_call_count += 1
        self.received_shop_id = shop_id
        self.received_service_id = service_id
        self.received_customer = customer
        self.received_booking_date = booking_date
        self.received_start_time = start_time
        if self.error is not None:
            raise self.error
        return self.booking

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected lookup_booking call.")

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        raise AssertionError("Unexpected reschedule_booking call.")

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected cancel_booking call.")


def make_context() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=SHOP,
        service=SERVICE,
        customer=CUSTOMER,
        booking_date=BOOKING_DATE,
        start_time=START_TIME,
        pending_action="create_booking",
    )


def make_handler(fake: FakeBookingGateway) -> CreateBookingHandler:
    gateway: BookingGateway = fake
    return CreateBookingHandler(gateway)


@pytest.mark.asyncio
async def test_execute_creates_booking_and_updates_context_after_success() -> None:
    context = make_context()
    fake = FakeBookingGateway(BOOKING)

    result = await make_handler(fake).execute(context)

    assert fake.create_booking_call_count == 1
    assert fake.received_shop_id == SHOP_ID
    assert fake.received_service_id == SERVICE_ID
    assert fake.received_customer is CUSTOMER
    assert fake.received_booking_date == BOOKING_DATE
    assert fake.received_start_time == START_TIME
    assert result is BOOKING
    assert context.booking_id == BOOKING_ID
    assert context.state is BookingState.COMPLETED
    assert context.pending_action is None


@pytest.mark.asyncio
async def test_execute_rejects_invalid_state_without_calling_gateway() -> None:
    context = make_context()
    context.state = BookingState.COLLECTING_CUSTOMER
    fake = FakeBookingGateway(BOOKING)

    with pytest.raises(InvalidBookingStateError):
        await make_handler(fake).execute(context)

    assert fake.create_booking_call_count == 0
    assert context.state is BookingState.COLLECTING_CUSTOMER
    assert context.booking_id is None
    assert context.pending_action == "create_booking"


@pytest.mark.asyncio
async def test_execute_rejects_invalid_context_without_calling_gateway() -> None:
    context = make_context()
    context.customer = None
    fake = FakeBookingGateway(BOOKING)

    with pytest.raises(InvalidBookingDataError):
        await make_handler(fake).execute(context)

    assert fake.create_booking_call_count == 0
    assert context.state is BookingState.AWAITING_CONFIRMATION
    assert context.booking_id is None
    assert context.pending_action == "create_booking"


@pytest.mark.asyncio
async def test_gateway_failure_propagates_without_updating_context() -> None:
    error = BookingConflictError("The selected slot is no longer available.")
    context = make_context()
    context.booking_id = OLD_BOOKING_ID
    fake = FakeBookingGateway(BOOKING, error=error)

    with pytest.raises(BookingConflictError) as exc_info:
        await make_handler(fake).execute(context)

    assert exc_info.value is error
    assert fake.create_booking_call_count == 1
    assert context.state is BookingState.AWAITING_CONFIRMATION
    assert context.booking_id == OLD_BOOKING_ID
    assert context.pending_action == "create_booking"


@pytest.mark.asyncio
async def test_execute_preserves_booking_input_data() -> None:
    context = make_context()
    fake = FakeBookingGateway(BOOKING)

    await make_handler(fake).execute(context)

    assert context.shop is SHOP
    assert context.service is SERVICE
    assert context.customer is CUSTOMER
    assert context.booking_date is BOOKING_DATE
    assert context.start_time is START_TIME
