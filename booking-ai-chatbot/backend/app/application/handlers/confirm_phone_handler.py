"""Application handler for confirming a collected phone number."""

from app.domain.booking_context import BookingContext


class ConfirmPhoneHandler:
    """Confirms the current phone without changing dialog state."""

    def execute(self, context: BookingContext) -> None:
        """Mark the context phone as confirmed."""
        context.confirm_phone()
