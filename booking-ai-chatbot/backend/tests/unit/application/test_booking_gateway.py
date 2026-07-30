"""Contract tests for the booking gateway port."""

from datetime import date, time
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking, Customer, Service, Shop

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


def make_booking(status: str = "confirmed") -> Booking:
    return Booking(
        booking_id=BOOKING_ID,
        status=status,
        shop=SHOP,
        service=SERVICE,
        customer=CUSTOMER,
        booking_date=BOOKING_DATE,
        start_time=START_TIME,
    )


class FakeBookingGateway:
    """In-memory fake implementing the booking gateway contract."""

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        return [SHOP]

    async def search_services(
        self,
        shop_id: UUID,
        query: str | None = None,
    ) -> list[Service]:
        return [SERVICE]

    async def check_availability(
        self,
        shop_id: UUID,
        service_id: UUID,
        booking_date: date,
    ) -> list[time]:
        return [START_TIME]

    async def create_booking(
        self,
        shop_id: UUID,
        service_id: UUID,
        customer: Customer,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        return make_booking()

    async def lookup_booking(self, booking_id: UUID) -> Booking:
        return make_booking()

    async def reschedule_booking(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
    ) -> Booking:
        return make_booking()

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        return make_booking(status="cancelled")


class IncompleteBookingGateway:
    """Fake that intentionally does not satisfy the gateway protocol."""


if TYPE_CHECKING:
    valid_gateway: BookingGateway = FakeBookingGateway()
    invalid_gateway: BookingGateway = IncompleteBookingGateway()  # type: ignore[assignment]


def use_booking_gateway(gateway: BookingGateway) -> BookingGateway:
    """Accept the same abstraction that an application handler consumes."""
    return gateway


def test_complete_fake_is_accepted_as_booking_gateway() -> None:
    gateway = use_booking_gateway(FakeBookingGateway())

    assert isinstance(gateway, FakeBookingGateway)


@pytest.mark.asyncio
async def test_fake_gateway_methods_return_expected_domain_types() -> None:
    gateway: BookingGateway = FakeBookingGateway()

    shops = await gateway.search_shops()
    services = await gateway.search_services(SHOP_ID, query="aroma")
    available_times = await gateway.check_availability(
        SHOP_ID,
        SERVICE_ID,
        BOOKING_DATE,
    )
    created = await gateway.create_booking(
        SHOP_ID,
        SERVICE_ID,
        CUSTOMER,
        BOOKING_DATE,
        START_TIME,
    )
    found = await gateway.lookup_booking(BOOKING_ID)
    rescheduled = await gateway.reschedule_booking(
        BOOKING_ID,
        BOOKING_DATE,
        START_TIME,
    )
    cancelled = await gateway.cancel_booking(BOOKING_ID)

    assert all(isinstance(shop, Shop) for shop in shops)
    assert all(isinstance(service, Service) for service in services)
    assert all(isinstance(available_time, time) for available_time in available_times)
    assert isinstance(created, Booking)
    assert isinstance(found, Booking)
    assert isinstance(rescheduled, Booking)
    assert isinstance(cancelled, Booking)
    assert cancelled.status == "cancelled"
