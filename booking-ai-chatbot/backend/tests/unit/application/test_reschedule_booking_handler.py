"""Tests for the booking reschedule application handler."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.handlers.reschedule_booking_handler import (
    RescheduleBookingHandler,
)
from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking, Customer, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import (
    BookingConflictError,
    BookingNotFoundError,
    InvalidBookingDataError,
    InvalidBookingStateError,
)

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")
NEW_BOOKING_DATE = date(2099, 8, 2)
NEW_START_TIME = time(14, 30)
SHOP = Shop(shop_id=SHOP_ID, name="Central Spa")
SERVICE = Service(
    service_id=SERVICE_ID,
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)
CUSTOMER = Customer(phone="0901234567", name="Nguyen An")
RESCHEDULED_BOOKING = Booking(
    booking_id=BOOKING_ID,
    status="confirmed",
    shop=SHOP,
    service=SERVICE,
    customer=CUSTOMER,
    booking_date=NEW_BOOKING_DATE,
    start_time=NEW_START_TIME,
)


class FakeBookingGateway:
    """Booking gateway fake that records reschedule requests."""

    def __init__(
        self,
        booking: Booking,
        error: Exception | None = None,
    ) -> None:
        self.booking = booking
        self.error = error
        self.reschedule_booking_call_count = 0
        self.received_booking_id: UUID | None = None
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
        raise AssertionError("Unexpected create_booking call.")

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected lookup_booking call.")

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        self.reschedule_booking_call_count += 1
        self.received_booking_id = booking_id
        self.received_booking_date = booking_date
        self.received_start_time = start_time
        if self.error is not None:
            raise self.error
        return self.booking

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        raise AssertionError("Unexpected cancel_booking call.")


def make_context() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        booking_id=BOOKING_ID,
        pending_action="reschedule_booking",
    )


def make_handler(fake: FakeBookingGateway) -> RescheduleBookingHandler:
    gateway: BookingGateway = fake
    return RescheduleBookingHandler(gateway)


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
async def test_execute_reschedules_booking_without_context() -> None:
    fake = FakeBookingGateway(RESCHEDULED_BOOKING)

    result = await make_handler(fake).execute(
        BOOKING_ID,
        NEW_BOOKING_DATE,
        NEW_START_TIME,
    )

    assert fake.reschedule_booking_call_count == 1
    assert fake.received_booking_id == BOOKING_ID
    assert fake.received_booking_date == NEW_BOOKING_DATE
    assert fake.received_start_time == NEW_START_TIME
    assert result is RESCHEDULED_BOOKING


@pytest.mark.asyncio
async def test_execute_updates_context_after_success() -> None:
    context = make_context()
    fake = FakeBookingGateway(RESCHEDULED_BOOKING)

    result = await make_handler(fake).execute(
        BOOKING_ID,
        NEW_BOOKING_DATE,
        NEW_START_TIME,
        context,
    )

    assert result is RESCHEDULED_BOOKING
    assert context.booking_id == BOOKING_ID
    assert context.shop is SHOP
    assert context.service is SERVICE
    assert context.customer is CUSTOMER
    assert context.booking_date is NEW_BOOKING_DATE
    assert context.start_time is NEW_START_TIME
    assert context.state is BookingState.COMPLETED
    assert context.pending_action is None


@pytest.mark.asyncio
async def test_execute_rejects_invalid_state_before_gateway_call() -> None:
    context = make_context()
    context.state = BookingState.COMPLETED
    original_values = context_values(context)
    fake = FakeBookingGateway(RESCHEDULED_BOOKING)

    with pytest.raises(InvalidBookingStateError):
        await make_handler(fake).execute(
            BOOKING_ID,
            NEW_BOOKING_DATE,
            NEW_START_TIME,
            context,
        )

    assert fake.reschedule_booking_call_count == 0
    assert context_values(context) == original_values


@pytest.mark.asyncio
async def test_execute_rejects_past_datetime_before_gateway_call() -> None:
    context = make_context()
    original_values = context_values(context)
    fake = FakeBookingGateway(RESCHEDULED_BOOKING)

    with pytest.raises(InvalidBookingDataError):
        await make_handler(fake).execute(
            BOOKING_ID,
            date(2000, 1, 1),
            time(10, 0),
            context,
        )

    assert fake.reschedule_booking_call_count == 0
    assert context_values(context) == original_values


@pytest.mark.parametrize(
    "error",
    [
        BookingNotFoundError("Booking was not found."),
        BookingConflictError("The selected slot is no longer available."),
    ],
)
@pytest.mark.asyncio
async def test_gateway_error_propagates_without_changing_context(
    error: Exception,
) -> None:
    context = make_context()
    original_values = context_values(context)
    fake = FakeBookingGateway(RESCHEDULED_BOOKING, error=error)

    with pytest.raises(type(error)) as exc_info:
        await make_handler(fake).execute(
            BOOKING_ID,
            NEW_BOOKING_DATE,
            NEW_START_TIME,
            context,
        )

    assert exc_info.value is error
    assert fake.reschedule_booking_call_count == 1
    assert context_values(context) == original_values
