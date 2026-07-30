"""Application handler for completing a booking conversation."""

from app.domain.booking import Booking
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState


class CompleteBookingHandler:
    """Completes a conversation using an official booking."""

    def execute(
        self,
        context: BookingContext,
        booking: Booking,
    ) -> Booking:
        """Synchronize an official booking into its conversation context."""
        context.booking_id = booking.booking_id
        context.shop = booking.shop
        context.service = booking.service
        context.customer = booking.customer
        context.booking_date = booking.booking_date
        context.start_time = booking.start_time
        context.state = BookingState.COMPLETED
        context.pending_action = None

        return booking
