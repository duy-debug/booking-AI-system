"""Tests for booking conversation states."""

import pytest

from app.domain.booking_state import BookingState

EXPECTED_STATES = {
    BookingState.IDLE: "idle",
    BookingState.SELECTING_SHOP: "selecting_shop",
    BookingState.SELECTING_DATE: "selecting_date",
    BookingState.SELECTING_PEOPLE: "selecting_people",
    BookingState.SELECTING_DURATION: "selecting_duration",
    BookingState.SELECTING_SERVICE: "selecting_service",
    BookingState.SELECTING_TIME: "selecting_time",
    BookingState.SELECTING_THERAPIST: "selecting_therapist",
    BookingState.SELECTING_OPTIONS: "selecting_options",
    BookingState.COLLECTING_PHONE: "collecting_phone",
    BookingState.VERIFYING_PHONE: "verifying_phone",
    BookingState.AWAITING_CONFIRMATION: "awaiting_confirmation",
    BookingState.BOOKING_EXECUTING: "booking_executing",
    BookingState.COMPLETED: "completed",
    BookingState.BOOKING_FAILED: "booking_failed",
    BookingState.CANCELLED: "cancelled",
}


def test_each_booking_state_has_expected_string_value() -> None:
    for state, expected_value in EXPECTED_STATES.items():
        assert state.value == expected_value


def test_booking_state_behaves_as_string() -> None:
    assert isinstance(BookingState.SELECTING_SHOP, str)
    assert BookingState.SELECTING_SHOP == "selecting_shop"


def test_booking_state_can_be_created_from_valid_string() -> None:
    assert BookingState("awaiting_confirmation") is BookingState.AWAITING_CONFIRMATION


def test_invalid_string_raises_value_error() -> None:
    with pytest.raises(ValueError):
        BookingState("invalid_state")


def test_booking_state_has_expected_number_of_members() -> None:
    assert len(BookingState) == 16


def test_booking_state_values_are_unique() -> None:
    values = [state.value for state in BookingState]

    assert len(values) == len(set(values))
