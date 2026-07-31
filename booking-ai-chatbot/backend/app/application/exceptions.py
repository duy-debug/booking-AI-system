"""Framework-independent application exceptions."""

from datetime import time


class ApplicationError(Exception):
    """Base exception for application use-case failures."""


class SlotConflictError(ApplicationError):
    """Raised when the selected slot fails the final availability check."""

    def __init__(
        self,
        nearest_slots: tuple[time, ...] = (),
        reason: str | None = None,
    ) -> None:
        super().__init__(reason or "The selected slot is no longer available.")
        self.nearest_slots = nearest_slots
        self.reason = reason


class CustomerVerificationMismatchError(ApplicationError):
    """Raised when POS verification returns data for a different phone."""


class InvalidIdempotencyKeyError(ApplicationError):
    """Raised when booking creation receives an empty idempotency key."""
