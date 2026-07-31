"""States used by the booking conversation flow."""

from enum import StrEnum


class BookingState(StrEnum):
    """Represents a state in the booking conversation."""

    IDLE = "idle"
    SELECTING_SHOP = "selecting_shop"
    SELECTING_DATE = "selecting_date"
    SELECTING_PEOPLE = "selecting_people"
    SELECTING_DURATION = "selecting_duration"
    SELECTING_SERVICE = "selecting_service"
    SELECTING_TIME = "selecting_time"
    SELECTING_THERAPIST = "selecting_therapist"
    COLLECTING_PHONE = "collecting_phone"
    VERIFYING_PHONE = "verifying_phone"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    BOOKING_EXECUTING = "booking_executing"
    COMPLETED = "completed"
    BOOKING_FAILED = "booking_failed"
    CANCELLED = "cancelled"
