"""Tests for domain exception inheritance."""

import pytest

from app.domain.exceptions import (
    BookingConflictError,
    BookingNotFoundError,
    DomainError,
    InvalidBookingDataError,
    InvalidBookingStateError,
)


@pytest.mark.parametrize(
    "exception_type",
    [
        InvalidBookingDataError,
        InvalidBookingStateError,
        BookingNotFoundError,
        BookingConflictError,
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
    ],
)
def test_booking_exceptions_can_be_caught_as_domain_error(
    exception: DomainError,
) -> None:
    with pytest.raises(DomainError):
        raise exception
