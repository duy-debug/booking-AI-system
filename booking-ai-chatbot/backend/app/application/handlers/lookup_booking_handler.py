"""Application handler for looking up an official booking."""

from uuid import UUID

from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState


class LookupBookingHandler:
    """Coordinates the booking lookup use case."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self,
        booking_id: UUID,
        context: BookingContext | None = None,
    ) -> Booking:
        """Look up a booking and optionally update its conversation context."""
        booking = await self._booking_gateway.lookup_booking(
            booking_id=booking_id,
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
