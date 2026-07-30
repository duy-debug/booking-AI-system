"""Tests for the booking cancellation application handler."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.handlers.cancel_booking_handler import CancelBookingHandler
from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking, Customer, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import (
    BookingConflictError,
    BookingNotFoundError,
    InvalidBookingStateError,
)

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
CANCELLED_BOOKING = Booking(
    booking_id=BOOKING_ID,
    status="cancelled",
    shop=SHOP,
    service=SERVICE,
    customer=CUSTOMER,
    booking_date=BOOKING_DATE,
    start_time=START_TIME,
)


class FakeBookingGateway:
    """Booking gateway fake that records cancellation requests."""

    def __init__(
        self,
        booking: Booking,
        error: Exception | None = None,
    ) -> None:
        self.booking = booking
        self.error = error
        self.cancel_booking_call_count = 0
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
        raise AssertionError("Unexpected lookup_booking call.")

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        raise AssertionError("Unexpected reschedule_booking call.")

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        self.cancel_booking_call_count += 1
        self.received_booking_id = booking_id
        if self.error is not None:
            raise self.error
        return self.booking


def make_context() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        booking_id=ORIGINAL_BOOKING_ID,
        pending_action="cancel_booking",
    )


def make_handler(fake: FakeBookingGateway) -> CancelBookingHandler:
    gateway: BookingGateway = fake
    return CancelBookingHandler(gateway)


def context_values(context: BookingContext) -> tuple[object, ...]:
    return (
        context.booking_id,
        context.shop,
        context.service,
        context.customer,
        context.booking_date,
        context.start_time,
        context.state,
        context.pending_action,
    )


@pytest.mark.asyncio
async def test_execute_cancels_booking_without_context() -> None:
    fake = FakeBookingGateway(CANCELLED_BOOKING)

    result = await make_handler(fake).execute(BOOKING_ID)

    assert fake.cancel_booking_call_count == 1
    assert fake.received_booking_id == BOOKING_ID
    assert result is CANCELLED_BOOKING


@pytest.mark.asyncio
async def test_execute_updates_context_without_resetting_booking_data() -> None:
    context = make_context()
    fake = FakeBookingGateway(CANCELLED_BOOKING)

    result = await make_handler(fake).execute(BOOKING_ID, context)

    assert result is CANCELLED_BOOKING
    assert context.booking_id == BOOKING_ID
    assert context.shop is SHOP
    assert context.service is SERVICE
    assert context.customer is CUSTOMER
    assert context.booking_date is BOOKING_DATE
    assert context.start_time is START_TIME
    assert context.state is BookingState.CANCELLED
    assert context.pending_action is None


@pytest.mark.asyncio
async def test_execute_rejects_invalid_state_before_gateway_call() -> None:
    context = make_context()
    context.state = BookingState.COMPLETED
    original_values = context_values(context)
    fake = FakeBookingGateway(CANCELLED_BOOKING)

    with pytest.raises(InvalidBookingStateError):
        await make_handler(fake).execute(BOOKING_ID, context)

    assert fake.cancel_booking_call_count == 0
    assert context_values(context) == original_values


@pytest.mark.parametrize(
    "error",
    [
        BookingNotFoundError("Booking was not found."),
        BookingConflictError("Booking cannot be cancelled."),
    ],
)
@pytest.mark.asyncio
async def test_gateway_error_propagates_without_changing_context(
    error: Exception,
) -> None:
    context = make_context()
    original_values = context_values(context)
    fake = FakeBookingGateway(CANCELLED_BOOKING, error=error)

    with pytest.raises(type(error)) as exc_info:
        await make_handler(fake).execute(BOOKING_ID, context)

    assert exc_info.value is error
    assert fake.cancel_booking_call_count == 1
    assert context_values(context) == original_values


@pytest.mark.asyncio
async def test_execute_does_not_rewrite_status_returned_by_gateway() -> None:
    backend_booking = Booking(
        booking_id=BOOKING_ID,
        status="confirmed",
        shop=SHOP,
        service=SERVICE,
        customer=CUSTOMER,
        booking_date=BOOKING_DATE,
        start_time=START_TIME,
    )
    context = make_context()
    fake = FakeBookingGateway(backend_booking)

    result = await make_handler(fake).execute(BOOKING_ID, context)

    assert result is backend_booking
    assert result.status == "confirmed"
    assert context.state is BookingState.CANCELLED
