"""Tests for the service search application handler."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.handlers.search_service_handler import SearchServiceHandler
from app.application.ports.booking_gateway import (
    AvailabilityRequest,
    BookingGateway,
    CourseSearchRequest,
    CreateBookingRequest,
    CreateBookingResult,
    CustomerVerificationRequest,
    CustomerVerificationResult,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
)
from app.domain.booking import Booking, CourseType, Service, Shop
from app.domain.exceptions import InvalidBookingDataError

SHOP_ID = UUID("11111111-1111-1111-1111-111111111111")
BOOKING_DATE = date(2026, 8, 1)
SERVICE = Service(
    service_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)


class FakeBookingGateway:
    """Booking gateway fake that records service searches."""

    def __init__(
        self,
        services: list[Service],
        error: InvalidBookingDataError | None = None,
    ) -> None:
        self.services = services
        self.error = error
        self.search_services_call_count = 0
        self.received_request: CourseSearchRequest | None = None

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        raise AssertionError("Unexpected search_shops call.")

    async def search_services(
        self,
        request: CourseSearchRequest,
    ) -> list[Service]:
        self.search_services_call_count += 1
        self.received_request = request
        if self.error is not None:
            raise self.error
        return self.services

    async def get_available_slots(
        self,
        request: AvailabilityRequest,
    ) -> tuple[time, ...]:
        raise AssertionError("Unexpected get_available_slots call.")

    async def verify_customer(
        self,
        request: CustomerVerificationRequest,
    ) -> CustomerVerificationResult:
        raise AssertionError("Unexpected verify_customer call.")

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        raise AssertionError("Unexpected check_final_availability call.")

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
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


def make_handler(fake: FakeBookingGateway) -> SearchServiceHandler:
    gateway: BookingGateway = fake
    return SearchServiceHandler(gateway)


@pytest.mark.asyncio
async def test_execute_maps_pos_request_and_filters_query_locally() -> None:
    other = Service(
        service_id=UUID("33333333-3333-3333-3333-333333333333"),
        name="Head spa",
        duration_minutes=30,
        price=Decimal("250000.00"),
    )
    services = [SERVICE, other]
    fake = FakeBookingGateway(services)

    result = await make_handler(fake).execute(
        SHOP_ID,
        "  AROMA  ",
        course_type=CourseType.MAIN,
        is_active=True,
    )

    assert fake.search_services_call_count == 1
    assert fake.received_request == CourseSearchRequest(
        shop_id=SHOP_ID,
        course_type=CourseType.MAIN,
        is_active=True,
    )
    assert result == [SERVICE]
    assert result[0] is SERVICE


@pytest.mark.asyncio
async def test_execute_without_query_returns_original_gateway_list() -> None:
    services = [SERVICE]
    fake = FakeBookingGateway(services)

    result = await make_handler(fake).execute(SHOP_ID)

    assert fake.search_services_call_count == 1
    assert fake.received_request == CourseSearchRequest(shop_id=SHOP_ID)
    assert result is services


@pytest.mark.asyncio
async def test_execute_returns_same_empty_list_from_gateway() -> None:
    services: list[Service] = []
    fake = FakeBookingGateway(services)

    result = await make_handler(fake).execute(SHOP_ID)

    assert result is services
    assert result == []


@pytest.mark.asyncio
async def test_execute_propagates_domain_exception() -> None:
    error = InvalidBookingDataError("Invalid service search.")
    fake = FakeBookingGateway([], error=error)

    with pytest.raises(InvalidBookingDataError) as exc_info:
        await make_handler(fake).execute(SHOP_ID, "invalid")

    assert exc_info.value is error
    assert fake.search_services_call_count == 1
