"""Tests for resolving parsed declarative transitions."""

import pytest

from app.dialog.flow_loader import (
    FlowAutoTransition,
    FlowCondition,
    FlowDefinition,
    FlowOnEnter,
    FlowState,
    FlowTransition,
    PhoneSplitConfig,
)
from app.dialog.state_machine import StateMachine
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.exceptions import InvalidBookingStateError


def _flow() -> FlowDefinition:
    exact_first = FlowTransition(
        "select_store",
        BookingState.SELECTING_DATE,
        ("handle_store_selection",),
        (FlowCondition(field="shop", op="not_null"),),
    )
    exact_second = FlowTransition(
        "select_store",
        BookingState.CANCELLED,
        ("must_not_run",),
    )
    wildcard = FlowTransition("*", BookingState.SELECTING_SHOP, ("clarify",))
    auto = FlowAutoTransition(
        condition=FlowCondition(field="num_customer", op="gte", value=2),
        target=BookingState.SELECTING_OPTIONS,
        actions=("skip_therapist_for_group",),
    )
    return FlowDefinition(
        version="2.0",
        name="test",
        description=None,
        initial_state=BookingState.SELECTING_SHOP,
        states={
            BookingState.SELECTING_SHOP: FlowState(
                description=None,
                on_enter=FlowOnEnter("ask_shop"),
                transitions=(exact_first, exact_second, wildcard),
            ),
            BookingState.SELECTING_THERAPIST: FlowState(
                description=None,
                on_enter=FlowOnEnter("ask_therapist"),
                transitions=(),
                auto_transitions=(auto,),
                phone_split_mode=PhoneSplitConfig(3, 3, 5000),
            ),
            BookingState.SELECTING_DATE: FlowState(
                description=None,
                on_enter=FlowOnEnter(),
                transitions=(),
            ),
        },
    )


def test_resolve_transition_returns_first_exact_match_without_evaluating_condition() -> None:
    transition = StateMachine(_flow()).resolve_transition(
        BookingState.SELECTING_SHOP,
        "select_store",
    )

    assert transition.target is BookingState.SELECTING_DATE
    assert transition.conditions[0].op == "not_null"


def test_resolve_transition_uses_wildcard() -> None:
    transition = StateMachine(_flow()).resolve_transition(
        BookingState.SELECTING_SHOP,
        "unknown",
    )

    assert transition.intent == "*"
    assert transition.target is BookingState.SELECTING_SHOP


def test_missing_transition_raises() -> None:
    with pytest.raises(InvalidBookingStateError):
        StateMachine(_flow()).resolve_transition(
            BookingState.SELECTING_DATE,
            "unknown",
        )


def test_transition_updates_only_state_and_returns_definition() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SHOP,
        pending_action="keep",
    )

    transition = StateMachine(_flow()).transition(context, "select_store")

    assert transition.actions == ("handle_store_selection",)
    assert context.state is BookingState.SELECTING_DATE
    assert context.pending_action == "keep"


def test_available_events_preserve_insertion_order() -> None:
    assert StateMachine(_flow()).available_events(BookingState.SELECTING_SHOP) == (
        "select_store",
        "select_store",
        "*",
    )


def test_can_transition_includes_wildcard() -> None:
    machine = StateMachine(_flow())

    assert machine.can_transition(BookingState.SELECTING_SHOP, "anything") is True
    assert machine.can_transition(BookingState.SELECTING_DATE, "anything") is False


def test_get_state_definition_and_auto_transitions() -> None:
    machine = StateMachine(_flow())

    state = machine.get_state_definition(BookingState.SELECTING_THERAPIST)
    auto = machine.get_auto_transitions(BookingState.SELECTING_THERAPIST)

    assert state.on_enter.instruction_template == "ask_therapist"
    assert auto[0].condition.value == 2
    assert auto[0].actions == ("skip_therapist_for_group",)


def test_get_phone_split_config_only_returns_configuration() -> None:
    config = StateMachine(_flow()).get_phone_split_config(
        BookingState.SELECTING_THERAPIST
    )

    assert config == PhoneSplitConfig(3, 3, 5000)


def test_unknown_state_definition_raises() -> None:
    with pytest.raises(InvalidBookingStateError):
        StateMachine(_flow()).get_state_definition(BookingState.COMPLETED)
