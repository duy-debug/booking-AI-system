"""Temporary booking data collected during a conversation."""

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from app.domain.booking import Customer, Service, Shop
from app.domain.booking_state import BookingState


@dataclass(slots=True)
class BookingContext:
    """Stores mutable booking data for an active conversation."""

    conversation_id: str
    state: BookingState = BookingState.IDLE
    shop: Shop | None = None
    service: Service | None = None
    customer: Customer | None = None
    booking_date: date | None = None
    start_time: time | None = None
    booking_id: UUID | None = None
    pending_action: str | None = None

    def is_ready_to_create(self) -> bool:
        """Return whether all data required to create a booking is present."""
        return all(
            value is not None
            for value in (
                self.shop,
                self.service,
                self.customer,
                self.booking_date,
                self.start_time,
            )
        )

    def reset(self) -> None:
        """Clear temporary booking data while preserving the conversation ID."""
        self.state = BookingState.IDLE
        self.shop = None
        self.service = None
        self.customer = None
        self.booking_date = None
        self.start_time = None
        self.booking_id = None
        self.pending_action = None
