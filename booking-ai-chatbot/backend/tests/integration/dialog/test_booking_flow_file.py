"""Integration tests for the detailed runtime booking flow."""

from pathlib import Path
from typing import cast

import pytest

from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.handlers.collect_customer_handler import CollectCustomerHandler
from app.application.handlers.confirm_phone_handler import ConfirmPhoneHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.dialog.flow_loader import (
    FlowDefinition,
    FlowFailure,
    FlowLoader,
    FlowTransition,
)
from app.dialog.state_machine import StateMachine
from app.dialog.tool_bridge import ToolBridge
from app.domain.booking import Booking
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState

FLOW_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "dialog"
    / "flows"
    / "booking-flow.json"
)
CONVERSATIONAL_STATES = (
    BookingState.SELECTING_SHOP,
    BookingState.SELECTING_DATE,
    BookingState.SELECTING_PEOPLE,
    BookingState.SELECTING_DURATION,
    BookingState.SELECTING_SERVICE,
    BookingState.SELECTING_TIME,
    BookingState.SELECTING_THERAPIST,
    BookingState.COLLECTING_PHONE,
    BookingState.VERIFYING_PHONE,
    BookingState.AWAITING_CONFIRMATION,
    BookingState.BOOKING_FAILED,
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


def _failure(transition: FlowTransition, condition: str) -> FlowFailure:
    for failure in transition.on_fail:
        if failure.condition == condition:
            return failure
    pytest.fail(f"Missing failure condition '{condition}'.")


def _all_declared_actions(flow: FlowDefinition) -> tuple[str, ...]:
    actions: list[str] = []
    for state in flow.states.values():
        actions.extend(state.on_enter.actions)
        for failure in state.on_enter.on_fail:
            actions.extend(failure.actions)
        for transition in state.transitions:
            actions.extend(transition.actions)
            for failure in transition.on_fail:
                actions.extend(failure.actions)
        for auto_transition in state.auto_transitions:
            actions.extend(auto_transition.actions)
            for failure in auto_transition.on_fail:
                actions.extend(failure.actions)
    return tuple(actions)


def _all_failures(flow: FlowDefinition) -> tuple[FlowFailure, ...]:
    failures: list[FlowFailure] = []
    for state in flow.states.values():
        failures.extend(state.on_enter.on_fail)
        for transition in state.transitions:
            failures.extend(transition.on_fail)
        for auto_transition in state.auto_transitions:
            failures.extend(auto_transition.on_fail)
    return tuple(failures)


def test_flow_loads_all_booking_states(flow: FlowDefinition) -> None:
    assert flow.version == "2.0"
    assert flow.name == "booking-flow"
    assert flow.initial_state is BookingState.IDLE
    assert set(flow.states) == set(BookingState)
    assert len(flow.states) == 15
    assert "selecting_options" not in {state.value for state in flow.states}


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


@pytest.mark.parametrize("num_customer", [2, 3])
def test_group_booking_auto_skips_therapist(
    flow: FlowDefinition,
    num_customer: int,
) -> None:
    context = BookingContext(
        conversation_id="group-conversation",
        state=BookingState.SELECTING_THERAPIST,
        num_customer=num_customer,
    )

    auto = StateMachine(flow).resolve_auto_transition(context)

    assert auto is not None
    assert auto.target is BookingState.COLLECTING_PHONE
    assert auto.actions == ("skip_therapist_for_group",)
    assert context.state is BookingState.SELECTING_THERAPIST


def test_single_booking_does_not_auto_skip_therapist(flow: FlowDefinition) -> None:
    context = BookingContext(
        conversation_id="single-conversation",
        state=BookingState.SELECTING_THERAPIST,
        num_customer=1,
    )

    assert StateMachine(flow).resolve_auto_transition(context) is None
    assert context.state is BookingState.SELECTING_THERAPIST


def test_booking_result_resolves_success_auto_transition(
    flow: FlowDefinition,
) -> None:
    context = BookingContext(
        conversation_id="completed-conversation",
        state=BookingState.BOOKING_EXECUTING,
        booking=cast(Booking, object()),
    )

    transition = StateMachine(flow).resolve_auto_transition(context)

    assert transition is not None
    assert transition.condition.field == "booking"
    assert transition.condition.op == "not_null"
    assert transition.target is BookingState.COMPLETED
    assert context.state is BookingState.BOOKING_EXECUTING


def test_real_flow_resolution_requires_explicit_apply(
    flow: FlowDefinition,
) -> None:
    machine = StateMachine(flow)
    context = BookingContext(conversation_id="conversation-1")

    transition = machine.resolve_transition(context, "start_booking")

    assert transition.target is BookingState.SELECTING_SHOP
    assert context.state is BookingState.IDLE
    machine.apply_transition(context, transition)
    assert context.state is BookingState.SELECTING_SHOP


def test_single_booking_can_skip_therapist(flow: FlowDefinition) -> None:
    transition = _transition(flow, BookingState.SELECTING_THERAPIST, "deny")

    assert transition.target is BookingState.COLLECTING_PHONE
    assert transition.actions == ("skip_therapist",)


def test_service_selection_owns_addons_and_slot_loading(
    flow: FlowDefinition,
) -> None:
    transition = _transition(flow, BookingState.SELECTING_SERVICE, "select_course")

    assert transition.target is BookingState.SELECTING_TIME
    assert transition.actions == ("handle_service_selection", "load_time_slots")
    assert _failure(transition, "addon_without_main_course").target is (
        BookingState.SELECTING_SERVICE
    )
    assert _failure(transition, "combo_not_bookable").target is (
        BookingState.SELECTING_SERVICE
    )


def test_service_failure_contract_is_complete(flow: FlowDefinition) -> None:
    transition = _transition(flow, BookingState.SELECTING_SERVICE, "select_course")
    failures = {failure.condition: failure for failure in transition.on_fail}

    assert set(failures) == {
        "course_not_found",
        "main_course_missing",
        "addon_without_main_course",
        "combo_not_bookable",
        "service_duration_mismatch",
        "no_slots_available",
        "slot_api_error",
    }
    assert failures["combo_not_bookable"].actions == ("clear_course_for_reselect",)
    assert failures["service_duration_mismatch"].target is (
        BookingState.SELECTING_DURATION
    )
    assert failures["no_slots_available"].target is BookingState.SELECTING_DATE


def test_duration_step_accepts_course_without_loading_slots(
    flow: FlowDefinition,
) -> None:
    transition = _transition(flow, BookingState.SELECTING_DURATION, "select_course")

    assert transition.target is BookingState.SELECTING_SERVICE
    assert transition.actions == (
        "handle_service_selection",
        "infer_duration_from_service",
    )
    assert "load_time_slots" not in transition.actions
    assert {failure.condition for failure in transition.on_fail} == {
        "duration_not_multiple_15",
        "course_not_found",
        "addon_without_main_course",
    }


def test_no_transition_targets_removed_options_state(flow: FlowDefinition) -> None:
    targets = {
        transition.target.value
        for state in flow.states.values()
        for transition in state.transitions
    }
    targets.update(
        transition.target.value
        for state in flow.states.values()
        for transition in state.auto_transitions
    )

    assert "selecting_options" not in targets


def test_therapist_is_processed_after_time(flow: FlowDefinition) -> None:
    time_transition = _transition(flow, BookingState.SELECTING_TIME, "select_time")
    therapist_transition = _transition(
        flow,
        BookingState.SELECTING_THERAPIST,
        "select_therapist",
    )

    assert time_transition.target is BookingState.SELECTING_THERAPIST
    assert therapist_transition.target is BookingState.COLLECTING_PHONE


def test_time_selection_failure_contract(flow: FlowDefinition) -> None:
    transition = _transition(flow, BookingState.SELECTING_TIME, "select_time")
    unavailable = _failure(transition, "slot_unavailable")
    api_error = _failure(transition, "slot_api_error")

    assert unavailable.target is BookingState.SELECTING_TIME
    assert unavailable.actions == ("suggest_nearest_time",)
    assert unavailable.instruction_template == "slot_unavailable"
    assert api_error.target is BookingState.SELECTING_TIME
    assert api_error.actions == ()
    assert api_error.instruction_template == "slot_api_error"


def test_therapist_failure_and_time_reselection_contract(
    flow: FlowDefinition,
) -> None:
    selection = _transition(
        flow,
        BookingState.SELECTING_THERAPIST,
        "select_therapist",
    )
    unavailable = _failure(selection, "therapist_unavailable")
    not_found = _failure(selection, "therapist_not_found")
    reselection = _transition(
        flow,
        BookingState.SELECTING_THERAPIST,
        "select_time",
    )

    assert unavailable.instruction_template == "therapist_unavailable"
    assert not_found.instruction_template == "ask_therapist"
    assert reselection.target is BookingState.SELECTING_TIME
    assert reselection.actions == ("handle_time_selection",)


def test_invalid_phone_failure_returns_to_collection(flow: FlowDefinition) -> None:
    failure = _failure(
        _transition(flow, BookingState.COLLECTING_PHONE, "provide_phone"),
        "invalid_phone",
    )

    assert failure.condition == "invalid_phone"
    assert failure.target is BookingState.COLLECTING_PHONE
    assert failure.actions == ()
    assert failure.instruction_template == "phone_invalid"


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
    assert definition.auto_transitions == ()


@pytest.mark.parametrize("state", CONVERSATIONAL_STATES)
def test_conversational_states_have_faq_unknown_and_last_wildcard(
    flow: FlowDefinition,
    state: BookingState,
) -> None:
    intents = tuple(item.intent for item in flow.states[state].transitions)
    question = _transition(flow, state, "ask_question")
    unknown = _transition(flow, state, "unknown")
    wildcard = flow.states[state].transitions[-1]

    assert question.target is state
    assert question.actions == ("answer_question",)
    assert "unknown" in intents
    assert unknown.target is state
    assert unknown.actions == ("ask_to_clarify",)
    assert wildcard.intent == "*"
    assert wildcard.target is state
    assert wildcard.actions == ("log_unhandled", "ask_to_clarify")


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
    assert "run_final_check" not in confirmation.actions
    assert confirmation.on_fail == ()
    assert confirmation.target is BookingState.BOOKING_EXECUTING
    assert confirmation.target is not BookingState.COMPLETED
    assert executing.on_enter.actions == ("create_booking",)
    assert executing.auto_transitions[0].target is BookingState.COMPLETED
    assert executing.auto_transitions[0].on_fail[0].target is BookingState.BOOKING_FAILED

    assert _all_declared_actions(flow).count("create_booking") == 1


def test_removed_option_actions_are_not_used(flow: FlowDefinition) -> None:
    actions = set(_all_declared_actions(flow))

    assert actions.isdisjoint(
        {
            "handle_options_selection",
            "keep_current_options",
            "skip_options",
            "ask_options",
        }
    )


def test_tool_bridge_audits_declared_actions_without_reading_json(
    flow: FlowDefinition,
) -> None:
    bridge = ToolBridge(
        check_availability_handler=cast(CheckAvailabilityHandler, object()),
        collect_customer_handler=cast(CollectCustomerHandler, object()),
        confirm_phone_handler=cast(ConfirmPhoneHandler, object()),
        create_booking_handler=cast(CreateBookingHandler, object()),
    )
    declared_actions = _all_declared_actions(flow)
    unregistered = bridge.find_unregistered_actions(declared_actions)

    assert len(set(declared_actions)) == 33
    assert {
        "load_time_slots",
        "handle_phone_collection",
        "mark_phone_confirmed",
        "create_booking",
    }.isdisjoint(unregistered)
    assert "run_final_check" not in declared_actions
    assert "complete_booking" not in declared_actions


def test_flow_failure_metadata_is_safe_and_resolvable(
    flow: FlowDefinition,
) -> None:
    failures = _all_failures(flow)

    assert failures
    assert all(failure.target in flow.states for failure in failures)
    assert all(
        failure.instruction_template is None
        or bool(failure.instruction_template.strip())
        for failure in failures
    )
    assert all(
        not {"create_booking", "retry_booking"}.intersection(failure.actions)
        for failure in failures
    )

    for state in flow.states.values():
        on_enter_codes = tuple(
            failure.condition for failure in state.on_enter.on_fail
        )
        assert len(on_enter_codes) == len(set(on_enter_codes))
        for transition in state.transitions:
            codes = tuple(failure.condition for failure in transition.on_fail)
            assert len(codes) == len(set(codes))
        for auto_transition in state.auto_transitions:
            codes = tuple(
                failure.condition for failure in auto_transition.on_fail
            )
            assert len(codes) == len(set(codes))


def test_real_flow_resolves_exact_failure_without_mutation(
    flow: FlowDefinition,
) -> None:
    context = BookingContext(
        conversation_id="failure-conversation",
        state=BookingState.SELECTING_TIME,
    )
    transition = _transition(flow, BookingState.SELECTING_TIME, "select_time")
    machine = StateMachine(flow)

    failure = machine.resolve_failure(transition, "slot_unavailable")

    assert failure is not None
    assert failure.target is BookingState.SELECTING_TIME
    assert failure.instruction_template == "slot_unavailable"
    assert context.state is BookingState.SELECTING_TIME


def test_declared_failure_codes_are_audited_against_mapper(
    flow: FlowDefinition,
) -> None:
    declared = {failure.condition for failure in _all_failures(flow)}
    mapped = set(ToolBridge().mapped_failure_codes())

    assert {
        "invalid_phone",
        "customer_ng_blocked",
        "customer_verification_mismatch",
        "booking_api_error",
        "slot_api_error",
        "slot_unavailable",
        "service_duration_mismatch",
    }.issubset(declared)
    assert {
        "invalid_phone",
        "customer_ng_blocked",
        "customer_verification_mismatch",
        "booking_api_error",
        "slot_api_error",
        "service_duration_mismatch",
    }.issubset(mapped)
    assert "course_not_found" in declared - mapped
    assert "booking_conflict" in mapped & declared


def test_booking_on_enter_failure_routing_is_declared(
    flow: FlowDefinition,
) -> None:
    executing = flow.states[BookingState.BOOKING_EXECUTING]
    failures = {
        failure.condition: failure for failure in executing.on_enter.on_fail
    }

    assert executing.on_enter.actions == ("create_booking",)
    assert failures["booking_conflict"].target is BookingState.SELECTING_TIME
    assert failures["booking_api_error"].target is BookingState.BOOKING_FAILED
    assert failures["booking_data_incomplete"].target is (
        BookingState.AWAITING_CONFIRMATION
    )
    assert failures["*"].target is BookingState.BOOKING_FAILED
    assert all(failure.actions == () for failure in failures.values())
