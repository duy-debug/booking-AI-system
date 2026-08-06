"""Tests for the shop search application handler."""

from datetime import date, time
from typing import cast
from uuid import UUID

import pytest

from app.application.handlers.search_shop_handler import SearchShopHandler
from app.domain.booking_models import (
    Booking,
    BookingGateway,
    Course,
    Customer,
    InvalidBookingDataError,
    Shop,
)

SHOP = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Central Spa",
    address="Central District",
)


class FakeBookingGateway:
    """Booking gateway fake that records shop searches."""

    def __init__(
        self,
        shops: list[Shop],
        error: InvalidBookingDataError | None = None,
    ) -> None:
        self.shops = shops
        self.error = error
        self.search_shops_call_count = 0
        self.received_query: str | None = None

    async def search_shops(self, query: str | None = None) -> list[Shop]:
        self.search_shops_call_count += 1
        self.received_query = query
        if self.error is not None:
            raise self.error
        return self.shops

    async def search_courses(
        self,
        shop_id: UUID,
        query: str | None = None,
    ) -> list[Course]:
        raise AssertionError("Unexpected search_courses call.")

    async def check_availability(
        self,
        shop_id: UUID,
        course_id: UUID,
        booking_date: date,
    ) -> list[time]:
        raise AssertionError("Unexpected check_availability call.")

    async def create_booking(
        self,
        shop_id: UUID,
        course_id: UUID,
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


def make_handler(fake: FakeBookingGateway) -> SearchShopHandler:
    return SearchShopHandler(cast(BookingGateway, fake))


@pytest.mark.asyncio
async def test_execute_fetches_catalog_once_and_filters_by_name() -> None:
    shops = [SHOP]
    fake = FakeBookingGateway(shops)

    result = await make_handler(fake).execute("central")

    assert fake.search_shops_call_count == 1
    assert fake.received_query is None
    assert result == shops
    assert result[0] is SHOP


@pytest.mark.asyncio
async def test_execute_filters_by_address_case_insensitively() -> None:
    fake = FakeBookingGateway([SHOP])

    result = await make_handler(fake).execute("DISTRICT")

    assert result == [SHOP]
    assert fake.received_query is None


@pytest.mark.asyncio
async def test_execute_filters_vietnamese_name_without_requiring_diacritics() -> None:
    shop = Shop(
        shop_id=UUID("22222222-2222-2222-2222-222222222222"),
        name="Komorebi Ba Đình",
        address="Hà Nội",
    )
    fake = FakeBookingGateway([shop])

    result = await make_handler(fake).execute("komorebi ba dinh")

    assert result == [shop]
    assert fake.received_query is None


@pytest.mark.asyncio
async def test_execute_returns_empty_when_local_query_does_not_match() -> None:
    fake = FakeBookingGateway([SHOP])

    result = await make_handler(fake).execute("missing")

    assert result == []


@pytest.mark.asyncio
async def test_execute_passes_none_query_to_gateway() -> None:
    fake = FakeBookingGateway([SHOP])

    await make_handler(fake).execute()

    assert fake.search_shops_call_count == 1
    assert fake.received_query is None


@pytest.mark.asyncio
async def test_execute_returns_same_empty_list_from_gateway() -> None:
    shops: list[Shop] = []
    fake = FakeBookingGateway(shops)

    result = await make_handler(fake).execute()

    assert result is shops
    assert result == []


@pytest.mark.asyncio
async def test_execute_removes_exact_duplicate_shop_names_only() -> None:
    duplicate = Shop(SHOP.shop_id, SHOP.name, "Another address")
    fake = FakeBookingGateway([SHOP, duplicate])

    result = await make_handler(fake).execute()

    assert result == [SHOP]


@pytest.mark.asyncio
async def test_execute_propagates_domain_exception() -> None:
    error = InvalidBookingDataError("Invalid shop search.")
    fake = FakeBookingGateway([], error=error)

    with pytest.raises(InvalidBookingDataError) as exc_info:
        await make_handler(fake).execute("invalid")

    assert exc_info.value is error
    assert fake.search_shops_call_count == 1
    assert fake.received_query is None
