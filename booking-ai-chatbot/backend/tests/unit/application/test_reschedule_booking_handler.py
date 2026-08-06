"""Tests for the consolidated rescheduling handler."""

from datetime import date, time
from typing import cast
from uuid import UUID

import pytest

from app.application.handlers.reschedule_booking_handler import RescheduleBookingHandler
from app.domain.booking_context import BookingContext
from app.domain.booking_models import BookingGateway
from app.domain.booking_state import BookingState
from tests.unit.application.test_cancel_booking_handler import BOOKING


class RescheduleGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, date, time]] = []

    async def reschedule_booking(
        self, booking_id: UUID, booking_date: date, start_time: time
    ) -> object:
        self.calls.append((booking_id, booking_date, start_time))
        return BOOKING


@pytest.mark.asyncio
async def test_reschedule_booking_updates_context_after_gateway_success() -> None:
    gateway = RescheduleGateway()
    context = BookingContext("conversation-1", state=BookingState.AWAITING_CONFIRMATION)
    new_date = date(2099, 8, 2)
    new_time = time(11, 0)

    result = await RescheduleBookingHandler(cast(BookingGateway, gateway)).execute(
        BOOKING.booking_id, new_date, new_time, context
    )

    assert result is BOOKING
    assert gateway.calls == [(BOOKING.booking_id, new_date, new_time)]
    assert context.state is BookingState.COMPLETED
