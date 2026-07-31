"""Tests for domain exception inheritance."""

import pytest

from app.domain.exceptions import (
    BookingConflictError,
    BookingContextNotReadyError,
    BookingNotFoundError,
    CustomerNotAllowedError,
    CustomerVerificationRequiredError,
    DomainError,
    InvalidBookingDataError,
    InvalidBookingStateError,
    InvalidCourseSelectionError,
    InvalidCustomerCountError,
    InvalidDurationError,
    PhoneNotConfirmedError,
    TherapistNotAllowedForGroupError,
)


@pytest.mark.parametrize(
    "exception_type",
    [
        InvalidBookingDataError,
        InvalidBookingStateError,
        BookingNotFoundError,
        BookingConflictError,
        InvalidCustomerCountError,
        InvalidDurationError,
        InvalidCourseSelectionError,
        TherapistNotAllowedForGroupError,
        PhoneNotConfirmedError,
        CustomerVerificationRequiredError,
        CustomerNotAllowedError,
        BookingContextNotReadyError,
    ],
)
def test_booking_exceptions_inherit_from_domain_error(
    exception_type: type[DomainError],
) -> None:
    assert issubclass(exception_type, DomainError)


@pytest.mark.parametrize(
    "exception",
    [
        InvalidBookingDataError(),
        InvalidBookingStateError(),
        BookingNotFoundError(),
        BookingConflictError(),
        InvalidCustomerCountError(),
        InvalidDurationError(),
        InvalidCourseSelectionError(),
        TherapistNotAllowedForGroupError(),
        PhoneNotConfirmedError(),
        CustomerVerificationRequiredError(),
        CustomerNotAllowedError(),
        BookingContextNotReadyError(),
    ],
)
def test_booking_exceptions_can_be_caught_as_domain_error(
    exception: DomainError,
) -> None:
    with pytest.raises(DomainError):
        raise exception
