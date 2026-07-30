"""Tests for booking conversation states."""

import pytest

from app.domain.booking_state import BookingState


EXPECTED_STATES = {
    BookingState.IDLE: "idle",
    BookingState.SELECTING_SHOP: "selecting_shop",
    BookingState.SELECTING_SERVICE: "selecting_service",
    BookingState.SELECTING_DATETIME: "selecting_datetime",
    BookingState.COLLECTING_CUSTOMER: "collecting_customer",
    BookingState.AWAITING_CONFIRMATION: "awaiting_confirmation",
    BookingState.COMPLETED: "completed",
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
    assert len(BookingState) == 8


def test_booking_state_values_are_unique() -> None:
    values = [state.value for state in BookingState]

    assert len(values) == len(set(values))
