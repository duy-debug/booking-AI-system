"""Tests for the availability check application handler."""

from datetime import date, time
from uuid import UUID

import pytest

from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking, Customer, Service, Shop
from app.domain.exceptions import InvalidBookingDataError

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
SERVICE_ID = UUID("22222222-2222-2222-2222-222222222222")
BOOKING_DATE = date(2026, 8, 1)
AVAILABLE_TIME = time(10, 30)


class FakeBookingGateway:
    """Booking gateway fake that records availability checks."""

    def __init__(
        self,
        available_times: list[time],
        error: InvalidBookingDataError | None = None,
    ) -> None:
        self.available_times = available_times
        self.error = error
        self.check_availability_call_count = 0
        self.received_shop_id: UUID | None = None
        self.received_service_id: UUID | None = None
        self.received_booking_date: date | None = None

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
        self.check_availability_call_count += 1
        self.received_shop_id = shop_id
        self.received_service_id = service_id
        self.received_booking_date = booking_date
        if self.error is not None:
            raise self.error
        return self.available_times

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
        raise AssertionError("Unexpected cancel_booking call.")


def make_handler(fake: FakeBookingGateway) -> CheckAvailabilityHandler:
    gateway: BookingGateway = fake
    return CheckAvailabilityHandler(gateway)


@pytest.mark.asyncio
async def test_execute_calls_gateway_once_with_expected_arguments() -> None:
    available_times = [AVAILABLE_TIME]
    fake = FakeBookingGateway(available_times)

    result = await make_handler(fake).execute(
        SHOP_ID,
        SERVICE_ID,
        BOOKING_DATE,
    )

    assert fake.check_availability_call_count == 1
    assert fake.received_shop_id == SHOP_ID
    assert fake.received_service_id == SERVICE_ID
    assert fake.received_booking_date == BOOKING_DATE
    assert result is available_times
    assert result[0] is AVAILABLE_TIME


@pytest.mark.asyncio
async def test_execute_returns_same_empty_list_from_gateway() -> None:
    available_times: list[time] = []
    fake = FakeBookingGateway(available_times)

    result = await make_handler(fake).execute(
        SHOP_ID,
        SERVICE_ID,
        BOOKING_DATE,
    )

    assert result is available_times
    assert result == []


@pytest.mark.asyncio
async def test_execute_propagates_domain_exception() -> None:
    error = InvalidBookingDataError("Invalid availability request.")
    fake = FakeBookingGateway([], error=error)

    with pytest.raises(InvalidBookingDataError) as exc_info:
        await make_handler(fake).execute(
            SHOP_ID,
            SERVICE_ID,
            BOOKING_DATE,
        )

    assert exc_info.value is error
    assert fake.check_availability_call_count == 1
