"""Tests for the customer collection application handler."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.handlers.collect_customer_handler import CollectCustomerHandler
from app.domain.booking import Customer, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import InvalidBookingDataError

SHOP = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Central Spa",
)
SERVICE = Service(
    service_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)
BOOKING_DATE = date(2026, 8, 1)
START_TIME = time(10, 30)


def make_complete_context_without_customer() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.COLLECTING_CUSTOMER,
        shop=SHOP,
        service=SERVICE,
        booking_date=BOOKING_DATE,
        start_time=START_TIME,
    )


def test_execute_creates_and_assigns_same_customer() -> None:
    context = BookingContext(conversation_id="conversation-1")

    result = CollectCustomerHandler().execute(
        context,
        phone="0901234567",
        name="Nguyen An",
    )

    assert isinstance(result, Customer)
    assert result.phone == "0901234567"
    assert result.name == "Nguyen An"
    assert context.customer is result


@pytest.mark.parametrize(
    ("phone", "expected_phone"),
    [
        ("090 123 4567", "0901234567"),
        ("090-123-4567", "0901234567"),
        ("+84 90-123-4567", "+84901234567"),
    ],
)
def test_execute_normalizes_phone(phone: str, expected_phone: str) -> None:
    context = BookingContext(conversation_id="conversation-1")

    customer = CollectCustomerHandler().execute(context, phone)

    assert customer.phone == expected_phone


def test_execute_trims_customer_name() -> None:
    context = BookingContext(conversation_id="conversation-1")

    customer = CollectCustomerHandler().execute(
        context,
        "0901234567",
        "  Nguyen An  ",
    )

    assert customer.name == "Nguyen An"


@pytest.mark.parametrize("name", ["", "   ", None])
def test_execute_converts_missing_or_blank_name_to_none(name: str | None) -> None:
    context = BookingContext(conversation_id="conversation-1")

    customer = CollectCustomerHandler().execute(context, "0901234567", name)

    assert customer.name is None


def test_invalid_phone_does_not_replace_existing_customer() -> None:
    original_customer = Customer(phone="0901234567", name="Original")
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.COLLECTING_CUSTOMER,
        customer=original_customer,
    )

    with pytest.raises(InvalidBookingDataError):
        CollectCustomerHandler().execute(context, "invalid-phone")

    assert context.customer is original_customer
    assert context.state is BookingState.COLLECTING_CUSTOMER


def test_execute_moves_complete_context_to_awaiting_confirmation() -> None:
    context = make_complete_context_without_customer()

    CollectCustomerHandler().execute(context, "0901234567")

    assert context.state is BookingState.AWAITING_CONFIRMATION


def test_execute_does_not_change_state_when_context_is_incomplete() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.COLLECTING_CUSTOMER,
    )

    CollectCustomerHandler().execute(context, "0901234567")

    assert context.state is BookingState.COLLECTING_CUSTOMER


def test_execute_preserves_existing_booking_selection() -> None:
    context = make_complete_context_without_customer()

    CollectCustomerHandler().execute(context, "0901234567")

    assert context.shop is SHOP
    assert context.service is SERVICE
    assert context.booking_date is BOOKING_DATE
    assert context.start_time is START_TIME
