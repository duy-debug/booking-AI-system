"""Application handler for cancelling an official booking."""

from uuid import UUID

from app.domain.booking_context import BookingContext
from app.domain.booking_models import Booking, BookingGateway, InvalidBookingStateError
from app.domain.booking_state import BookingState


class CancelBookingHandler:
    """Coordinate the booking cancellation use case."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(
        self, booking_id: UUID, context: BookingContext | None = None
    ) -> Booking:
        if context is not None and context.state is not BookingState.AWAITING_CONFIRMATION:
            raise InvalidBookingStateError("Booking context must be awaiting confirmation.")
        booking = await self._booking_gateway.cancel_booking(booking_id=booking_id)
        if context is not None:
            context.booking_id = booking.booking_id
            context.state = BookingState.CANCELLED
            context.pending_action = None
        return booking
