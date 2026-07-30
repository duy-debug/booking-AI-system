"""Tests for temporary booking conversation data."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.booking import Customer, Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState


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
CUSTOMER = Customer(phone="0901234567", name="Nguyen An")
BOOKING_ID = UUID("33333333-3333-3333-3333-333333333333")


def make_ready_context() -> BookingContext:
    return BookingContext(
        conversation_id="conversation-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=SHOP,
        service=SERVICE,
        customer=CUSTOMER,
        booking_date=date(2026, 8, 1),
        start_time=time(10, 30),
    )


def test_new_context_starts_idle() -> None:
    context = BookingContext(conversation_id="conversation-1")

    assert context.state is BookingState.IDLE


def test_booking_fields_default_to_none() -> None:
    context = BookingContext(conversation_id="conversation-1")

    assert context.shop is None
    assert context.service is None
    assert context.customer is None
    assert context.booking_date is None
    assert context.start_time is None
    assert context.booking_id is None
    assert context.pending_action is None


def test_context_is_not_ready_when_data_is_missing() -> None:
    context = make_ready_context()
    context.start_time = None

    assert context.is_ready_to_create() is False


def test_context_is_ready_when_required_data_is_present() -> None:
    assert make_ready_context().is_ready_to_create() is True


def test_reset_clears_temporary_booking_data() -> None:
    context = make_ready_context()
    context.booking_id = BOOKING_ID
    context.pending_action = "create_booking"

    context.reset()

    assert context.state is BookingState.IDLE
    assert context.shop is None
    assert context.service is None
    assert context.customer is None
    assert context.booking_date is None
    assert context.start_time is None
    assert context.booking_id is None
    assert context.pending_action is None


def test_reset_preserves_conversation_id() -> None:
    context = make_ready_context()

    context.reset()

    assert context.conversation_id == "conversation-1"


def test_context_data_is_mutable() -> None:
    context = BookingContext(conversation_id="conversation-1")

    context.shop = SHOP
    context.state = BookingState.SELECTING_SERVICE

    assert context.shop is SHOP
    assert context.state is BookingState.SELECTING_SERVICE


def test_slots_prevent_adding_undeclared_attributes() -> None:
    context = BookingContext(conversation_id="conversation-1")

    assert not hasattr(context, "__dict__")
    with pytest.raises(AttributeError):
        context.unexpected = "value"  # type: ignore[attr-defined]
