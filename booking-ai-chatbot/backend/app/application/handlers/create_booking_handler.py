"""Application handler for creating an official booking."""

from app.application.ports.booking_gateway import BookingGateway
from app.domain.booking import Booking
from app.domain.booking_context import BookingContext
from app.domain.booking_rules import BookingRules
from app.domain.booking_state import BookingState
from app.domain.exceptions import InvalidBookingStateError


class CreateBookingHandler:
    """Coordinates creation of an official booking."""

    def __init__(self, booking_gateway: BookingGateway) -> None:
        self._booking_gateway = booking_gateway

    async def execute(self, context: BookingContext) -> Booking:
        """Create a booking from a confirmed and valid context."""
        if context.state is not BookingState.AWAITING_CONFIRMATION:
            raise InvalidBookingStateError(
                "Booking context must be awaiting confirmation."
            )

        BookingRules.validate_create_context(context)

        assert context.shop is not None
        assert context.service is not None
        assert context.customer is not None
        assert context.booking_date is not None
        assert context.start_time is not None

        booking = await self._booking_gateway.create_booking(
            shop_id=context.shop.shop_id,
            service_id=context.service.service_id,
            customer=context.customer,
            booking_date=context.booking_date,
            start_time=context.start_time,
        )

        context.booking_id = booking.booking_id
        context.state = BookingState.COMPLETED
        context.pending_action = None

        return booking
