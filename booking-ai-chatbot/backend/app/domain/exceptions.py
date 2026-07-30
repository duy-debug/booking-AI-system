"""Framework-independent domain exceptions."""


class DomainError(Exception):
    """Base exception for all domain-level errors."""


class InvalidBookingDataError(DomainError):
    """Raised when booking data violates domain rules."""


class InvalidBookingStateError(DomainError):
    """Raised when an operation is invalid for the booking state."""


class BookingNotFoundError(DomainError):
    """Raised when a requested booking cannot be found."""


class BookingConflictError(DomainError):
    """Raised when a booking conflicts with an existing reservation."""
