"""Tests for the consolidated cancellation handler."""

from datetime import date, time
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from app.application.handlers.cancel_booking_handler import CancelBookingHandler
from app.domain.booking_context import BookingContext
from app.domain.booking_models import Booking, BookingGateway, Course, Customer, Shop
from app.domain.booking_state import BookingState

SHOP = Shop(UUID("11111111-1111-1111-1111-111111111111"), "Komorebi")
COURSE = Course(
    UUID("22222222-2222-2222-2222-222222222222"),
    "Massage đá nóng",
    60,
    Decimal("500000"),
)
BOOKING = Booking(
    UUID("33333333-3333-3333-3333-333333333333"),
    "cancelled",
    SHOP,
    COURSE,
    Customer("0901234567", "An"),
    date(2099, 8, 1),
    time(10, 0),
)


class CancelGateway:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def cancel_booking(self, booking_id: UUID) -> Booking:
        self.calls.append(booking_id)
        return BOOKING


@pytest.mark.asyncio
async def test_cancel_booking_updates_context_after_gateway_success() -> None:
    gateway = CancelGateway()
    context = BookingContext("conversation-1", state=BookingState.AWAITING_CONFIRMATION)

    result = await CancelBookingHandler(cast(BookingGateway, gateway)).execute(
        BOOKING.booking_id, context
    )

    assert result is BOOKING
    assert gateway.calls == [BOOKING.booking_id]
    assert context.state is BookingState.CANCELLED
