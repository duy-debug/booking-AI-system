"""Application handler for rescheduling an official booking."""

from datetime import date, time
from uuid import UUID

from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    Booking,
    BookingGateway,
    BookingRules,
    InvalidBookingStateError,
)
from app.domain.booking_state import BookingState


class RescheduleBookingHandler:
    """Coordinate the booking reschedule use case."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
        context: BookingContext | None = None,
    ) -> Booking:
        if context is not None and context.state is not BookingState.AWAITING_CONFIRMATION:
            raise InvalidBookingStateError("Booking context must be awaiting confirmation.")
        BookingRules.validate_booking_datetime(
            booking_date=booking_date, start_time=start_time
        )
        booking = await self._booking_gateway.reschedule_booking(
            booking_id=booking_id, booking_date=booking_date, start_time=start_time
        )
        if context is not None:
            context.booking_id = booking.booking_id
            context.booking_date = booking.booking_date
            context.start_time = booking.start_time
            context.state = BookingState.COMPLETED
            context.pending_action = None
        return booking
