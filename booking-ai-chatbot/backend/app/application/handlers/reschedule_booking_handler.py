"""Application handler for rescheduling an official booking."""

from datetime import date, time
from uuid import UUID

from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking
from app.domain.booking_context import BookingContext
from app.domain.booking_rules import BookingRules
from app.domain.booking_state import BookingState
from app.domain.exceptions import InvalidBookingStateError


class RescheduleBookingHandler:
    """Coordinates the booking reschedule use case."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        booking_id: UUID,
        booking_date: date,
        start_time: time,
        context: BookingContext | None = None,
    ) -> Booking:
        """Reschedule a booking and optionally update its context."""
        if (
            context is not None
            and context.state is not BookingState.AWAITING_CONFIRMATION
        ):
            raise InvalidBookingStateError(
                "Booking context must be awaiting confirmation."
            )

        BookingRules.validate_booking_datetime(
            booking_date=booking_date,
            start_time=start_time,
        )

        booking = await self._booking_gateway.reschedule_booking(
            booking_id=booking_id,
            booking_date=booking_date,
            start_time=start_time,
        )

        if context is not None:
            context.booking_id = booking.booking_id
            context.shop = booking.shop
            context.service = booking.service
            context.customer = booking.customer
            context.booking_date = booking.booking_date
            context.start_time = booking.start_time
            context.state = BookingState.COMPLETED
            context.pending_action = None

        return booking
