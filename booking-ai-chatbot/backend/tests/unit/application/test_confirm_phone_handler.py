"""Tests for explicit phone confirmation."""

import pytest

from app.application.handlers.confirm_phone_handler import ConfirmPhoneHandler
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import InvalidBookingDataError


def test_execute_confirms_phone_without_changing_state_or_verification() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.VERIFYING_PHONE,
        phone="0901234567",
        member_rank="gold",
        ng_list_checked=True,
    )

    ConfirmPhoneHandler().execute(context)

    assert context.phone_confirmed is True
    assert context.member_rank == "gold"
    assert context.ng_list_checked is True
    assert context.state is BookingState.VERIFYING_PHONE


def test_execute_requires_phone() -> None:
    context = BookingContext(conversation_id="conversation-1")

    with pytest.raises(InvalidBookingDataError):
        ConfirmPhoneHandler().execute(context)


def test_ng_customer_remains_not_ready_after_phone_confirmation() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        phone="0901234567",
        ng_list_checked=True,
        is_ng_customer=True,
    )

    ConfirmPhoneHandler().execute(context)

    assert context.phone_confirmed is True
    assert context.is_ng_customer is True
    assert context.is_ready_to_create() is False
