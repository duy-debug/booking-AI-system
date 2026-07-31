"""Integration tests for the detailed runtime booking flow."""

from pathlib import Path

import pytest

from app.dialog.flow_loader import FlowDefinition, FlowLoader, FlowTransition
from app.dialog.state_machine import StateMachine
from app.domain.booking_state import BookingState

FLOW_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "dialog"
    / "flows"
    / "booking-flow.json"
)
CONVERSATIONAL_STATES = tuple(
    state
    for state in BookingState
    if state
    not in {
        BookingState.BOOKING_EXECUTING,
        BookingState.COMPLETED,
        BookingState.CANCELLED,
    }
)


@pytest.fixture(scope="module")
def flow() -> FlowDefinition:
    return FlowLoader.load(FLOW_PATH)


def _transition(
    flow: FlowDefinition,
    state: BookingState,
    intent: str,
) -> FlowTransition:
    for transition in flow.states[state].transitions:
        if transition.intent == intent:
            return transition
    pytest.fail(f"Missing intent '{intent}' in state '{state.value}'.")


def test_flow_loads_all_booking_states(flow: FlowDefinition) -> None:
    assert flow.version == "2.0"
    assert flow.name == "booking-flow"
    assert flow.initial_state is BookingState.IDLE
    assert set(flow.states) == set(BookingState)
    assert len(flow.states) == 16


@pytest.mark.parametrize(
    ("state", "intent", "target"),
    [
        (BookingState.IDLE, "start_booking", BookingState.SELECTING_SHOP),
        (BookingState.SELECTING_SHOP, "select_store", BookingState.SELECTING_DATE),
        (
            BookingState.SELECTING_DATE,
            "select_date",
            BookingState.SELECTING_PEOPLE,
        ),
        (
            BookingState.SELECTING_PEOPLE,
            "select_people",
            BookingState.SELECTING_DURATION,
        ),
        (
            BookingState.SELECTING_DURATION,
            "select_duration",
            BookingState.SELECTING_SERVICE,
        ),
        (
            BookingState.SELECTING_SERVICE,
            "select_course",
            BookingState.SELECTING_TIME,
        ),
        (
            BookingState.SELECTING_TIME,
            "select_time",
            BookingState.SELECTING_THERAPIST,
        ),
        (
            BookingState.SELECTING_THERAPIST,
            "select_therapist",
            BookingState.SELECTING_OPTIONS,
        ),
        (
            BookingState.SELECTING_OPTIONS,
            "select_options",
            BookingState.COLLECTING_PHONE,
        ),
        (
            BookingState.COLLECTING_PHONE,
            "provide_phone",
            BookingState.VERIFYING_PHONE,
        ),
        (
            BookingState.VERIFYING_PHONE,
            "confirm",
            BookingState.AWAITING_CONFIRMATION,
        ),
        (
            BookingState.AWAITING_CONFIRMATION,
            "confirm",
            BookingState.BOOKING_EXECUTING,
        ),
        (
            BookingState.BOOKING_EXECUTING,
            "booking_succeeded",
            BookingState.COMPLETED,
        ),
    ],
)
def test_complete_happy_path(
    flow: FlowDefinition,
    state: BookingState,
    intent: str,
    target: BookingState,
) -> None:
    assert _transition(flow, state, intent).target is target


def test_group_booking_auto_skips_therapist(flow: FlowDefinition) -> None:
    auto = flow.states[BookingState.SELECTING_THERAPIST].auto_transitions[0]

    assert auto.condition.field == "num_customer"
    assert auto.condition.op == "gte"
    assert auto.condition.value == 2
    assert auto.target is BookingState.SELECTING_OPTIONS
    assert auto.actions == ("skip_therapist_for_group",)


@pytest.mark.parametrize("intent", ["select_options", "confirm", "deny"])
def test_options_are_optional(flow: FlowDefinition, intent: str) -> None:
    assert (
        _transition(flow, BookingState.SELECTING_OPTIONS, intent).target
        is BookingState.COLLECTING_PHONE
    )


def test_invalid_phone_failure_returns_to_collection(flow: FlowDefinition) -> None:
    failure = _transition(
        flow,
        BookingState.COLLECTING_PHONE,
        "provide_phone",
    ).on_fail[0]

    assert failure.condition == "invalid_phone"
    assert failure.target is BookingState.COLLECTING_PHONE
    assert failure.actions == ("phone_invalid",)


def test_phone_denial_returns_to_collection(flow: FlowDefinition) -> None:
    transition = _transition(flow, BookingState.VERIFYING_PHONE, "deny")

    assert transition.target is BookingState.COLLECTING_PHONE
    assert transition.actions == ("clear_phone_confirmation",)


def test_booking_failure_and_retry_paths(flow: FlowDefinition) -> None:
    failure = _transition(
        flow,
        BookingState.BOOKING_EXECUTING,
        "booking_failed",
    )
    retry = _transition(flow, BookingState.BOOKING_FAILED, "confirm")

    assert failure.target is BookingState.BOOKING_FAILED
    assert retry.target is BookingState.BOOKING_EXECUTING
    assert retry.actions == ("retry_booking",)


@pytest.mark.parametrize(
    "state",
    [BookingState.COMPLETED, BookingState.CANCELLED],
)
def test_terminal_states_have_no_transitions(
    flow: FlowDefinition,
    state: BookingState,
) -> None:
    definition = flow.states[state]

    assert definition.terminal is True
    assert definition.transitions == ()


@pytest.mark.parametrize("state", CONVERSATIONAL_STATES)
def test_conversational_states_have_unknown_and_last_wildcard(
    flow: FlowDefinition,
    state: BookingState,
) -> None:
    intents = tuple(item.intent for item in flow.states[state].transitions)

    assert "unknown" in intents
    assert intents[-1] == "*"


@pytest.mark.parametrize(
    "state",
    [
        BookingState.SELECTING_SHOP,
        BookingState.SELECTING_DATE,
        BookingState.SELECTING_PEOPLE,
        BookingState.SELECTING_DURATION,
        BookingState.SELECTING_SERVICE,
        BookingState.SELECTING_TIME,
        BookingState.SELECTING_THERAPIST,
        BookingState.SELECTING_OPTIONS,
        BookingState.COLLECTING_PHONE,
        BookingState.VERIFYING_PHONE,
        BookingState.AWAITING_CONFIRMATION,
    ],
)
def test_change_info_is_deferred_self_loop(
    flow: FlowDefinition,
    state: BookingState,
) -> None:
    transition = _transition(flow, state, "change_info")

    assert transition.target is state
    assert transition.actions == ("defer_change_info",)


def test_phone_split_configuration_is_loaded_but_not_executed(
    flow: FlowDefinition,
) -> None:
    machine = StateMachine(flow)
    config = machine.get_phone_split_config(BookingState.COLLECTING_PHONE)

    assert config is not None
    assert config.segment_count == 3
    assert config.max_full_resets == 3
    assert config.silence_timeout_ms == 5000
    assert machine.get_phone_split_config(BookingState.IDLE) is None


def test_booking_execution_owns_create_booking_action(flow: FlowDefinition) -> None:
    confirmation = _transition(
        flow,
        BookingState.AWAITING_CONFIRMATION,
        "confirm",
    )
    executing = flow.states[BookingState.BOOKING_EXECUTING]

    assert "create_booking" not in confirmation.actions
    assert executing.on_enter.actions == ("create_booking",)
    assert executing.auto_transitions[0].target is BookingState.COMPLETED
    assert executing.auto_transitions[0].on_fail[0].target is BookingState.BOOKING_FAILED
