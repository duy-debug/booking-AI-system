"""Framework-independent domain exceptions."""


class DomainError(Exception):
    """Base exception for all domain-level errors."""


class InvalidBookingDataError(DomainError):
    """Raised when booking data violates domain rules."""


class InvalidCustomerCountError(InvalidBookingDataError):
    """Raised when a booking has an unsupported number of customers."""


class InvalidDurationError(InvalidBookingDataError):
    """Raised when a booking duration violates domain rules."""


class InvalidCourseSelectionError(InvalidBookingDataError):
    """Raised when a main course and add-ons form an invalid selection."""


class TherapistNotAllowedForGroupError(InvalidBookingDataError):
    """Raised when a group booking specifies a therapist preference."""


class PhoneNotConfirmedError(InvalidBookingDataError):
    """Raised when booking creation is attempted with an unconfirmed phone."""


class CustomerVerificationRequiredError(InvalidBookingDataError):
    """Raised when member and NG-list verification has not completed."""


class CustomerNotAllowedError(InvalidBookingDataError):
    """Raised when customer verification disallows booking."""


class BookingContextNotReadyError(InvalidBookingDataError):
    """Raised when required booking context data is incomplete."""


class InvalidBookingStateError(DomainError):
    """Raised when an operation is invalid for the booking state."""


class BookingNotFoundError(DomainError):
    """Raised when a requested booking cannot be found."""


class BookingConflictError(DomainError):
    """Raised when a booking conflicts with an existing reservation."""
