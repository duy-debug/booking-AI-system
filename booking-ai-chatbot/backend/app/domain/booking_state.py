"""States used by the booking conversation flow."""

from enum import StrEnum


class BookingState(StrEnum):
    """Represents a state in the booking conversation."""

    IDLE = "idle"
    SELECTING_SHOP = "selecting_shop"
    SELECTING_SERVICE = "selecting_service"
    SELECTING_DATETIME = "selecting_datetime"
    COLLECTING_CUSTOMER = "collecting_customer"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
