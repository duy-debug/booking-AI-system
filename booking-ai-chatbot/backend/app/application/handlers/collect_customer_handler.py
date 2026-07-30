"""Application handler for collecting booking customer information."""

from app.domain.booking import Customer
from app.domain.booking_context import BookingContext
from app.domain.booking_rules import BookingRules
from app.domain.booking_state import BookingState


class CollectCustomerHandler:
    """Collects validated customer data into a booking context."""

    def execute(
        self,
        context: BookingContext,
        phone: str,
        name: str | None = None,
    ) -> Customer:
        """Validate, normalize, and store customer information."""
        BookingRules.validate_phone(phone)

        normalized_phone = "".join(phone.split()).replace("-", "")
        normalized_name = name.strip() or None if name is not None else None
        customer = Customer(phone=normalized_phone, name=normalized_name)

        context.customer = customer
        if context.is_ready_to_create():
            context.state = BookingState.AWAITING_CONFIRMATION

        return customer
