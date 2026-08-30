"""Integration tests for the detailed runtime booking flow."""

from pathlib import Path
from typing import cast

import pytest

from app.application.action_registry import ActionRegistry
from app.application.handlers.check_availability_handler import (
    CheckAvailabilityHandler,
)
from app.application.handlers.check_customer_handler import CheckCustomerHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.flow_loader import (
    FlowDefinition,
    FlowFailure,
    FlowLoader,
    FlowTransition,
)
from app.dialog.state_machine import StateMachine
from app.domain.booking_context import BookingContext
from app.domain.booking_models import Booking, BookingGateway, Customer
from app.domain.booking_state import BookingState

FLOW_PATH = Path(__file__).resolve().parents[3] / "app" / "dialog" / "booking_flow.json"
CHANGE_HANDLERS_PATH = FLOW_PATH
CONVERSATIONAL_STATES = (
    BookingState.AWAITING_CANCEL_CONFIRMATION,
    BookingState.SELECTING_SHOP,
    BookingState.SELECTING_DATE,
    BookingState.SELECTING_PEOPLE,
    BookingState.SELECTING_DURATION,
    BookingState.SELECTING_SERVICE,
    BookingState.SELECTING_TIME,
    BookingState.SELECTING_THERAPIST,
    BookingState.COLLECTING_PHONE,
    BookingState.AWAITING_CONFIRMATION,
    BookingState.BOOKING_FAILED,
)


def test_change_handlers_define_one_rule_per_supported_target() -> None:
    rules = FlowLoader.load_change_handlers(CHANGE_HANDLERS_PATH)

    assert set(rules) == {
        "shop",
        "date",
        "people",
        "duration",
        "main_course",
        "addon",
        "time",
        "therapist",
        "phone",
        "customer_name",
    }
    assert rules["date"].reset_action == "change_date"
    assert rules["date"].next_state is BookingState.SELECTING_DATE
    assert rules["date"].applied_state is BookingState.SELECTING_PEOPLE


@pytest.fixture(scope="module")
def flow() -> FlowDefinition:
    return FlowLoader.load(FLOW_PATH)


def _transition(
    flow: FlowDefinition,
    state: BookingState,
    intent: str,
) -> FlowTransition:
    fallback_transition: FlowTransition | None = None
    for transition in flow.states[state].transitions:
        if transition.intent == intent:
            if not transition.conditions:
                return transition
            if fallback_transition is None:
                fallback_transition = transition
    if fallback_transition is not None:
        return fallback_transition
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
    assert set(flow.states) == set(BookingState) - {BookingState.VERIFYING_PHONE}
    assert len(flow.states) == 17
    assert "selecting_options" not in {state.value for state in flow.states}


@pytest.mark.parametrize(
    ("state", "intent", "target"),
    [
        (BookingState.IDLE, "start_booking", BookingState.SELECTING_SHOP),
        (
            BookingState.COLLECTING_CANCEL_BOOKING_IDENTITY,
            "start_booking",
            BookingState.SELECTING_SHOP,
        ),
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
            BookingState.SELECTING_SERVICE,
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
            BookingState.COLLECTING_NAME,
        ),
        (
            BookingState.COLLECTING_NAME,
            "provide_name",
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


def test_cancel_booking_identity_lookup_requires_confirmation_before_cancel(
    flow: FlowDefinition,
) -> None:
    transition = _transition(flow, BookingState.IDLE, "cancel_existing_booking")

    assert transition.target is BookingState.AWAITING_CANCEL_CONFIRMATION
    assert transition.actions == ("lookup_existing_booking_for_cancel",)


def test_cancel_booking_confirmation_is_the_only_cancel_side_effect(
    flow: FlowDefinition,
) -> None:
    transition = _transition(
        flow,
        BookingState.AWAITING_CANCEL_CONFIRMATION,
        "confirm",
    )

    assert transition.target is BookingState.CANCELLED
    assert transition.actions == ("cancel_existing_booking",)


@pytest.mark.parametrize("num_customer", [2, 3])
def test_group_booking_skips_therapist_step(
    flow: FlowDefinition,
    num_customer: int,
) -> None:
    context = BookingContext(
        conversation_id="group-conversation",
        state=BookingState.SELECTING_TIME,
        num_customer=num_customer,
    )

    transition = StateMachine(flow).resolve_transition(context, "select_time")

    assert transition.target is BookingState.COLLECTING_PHONE
    assert transition.actions == ("handle_time_selection", "skip_therapist_for_group")


def test_single_booking_does_not_auto_skip_therapist(flow: FlowDefinition) -> None:
    context = BookingContext(
        conversation_id="single-conversation",
        state=BookingState.SELECTING_THERAPIST,
        num_customer=1,
    )

    assert StateMachine(flow).resolve_auto_transition(context) is None


def test_customer_name_step_skips_only_for_existing_customer(flow: FlowDefinition) -> None:
    machine = StateMachine(flow)
    existing = BookingContext(
        "existing",
        state=BookingState.COLLECTING_NAME,
        customer_id="customer-1",
    )
    first_time = BookingContext("new", state=BookingState.COLLECTING_NAME)

    transition = machine.resolve_auto_transition(existing)

    assert transition is not None
    assert transition.target is BookingState.AWAITING_CONFIRMATION
    assert machine.resolve_auto_transition(first_time) is None


def test_changed_phone_with_existing_name_returns_to_confirmation(
    flow: FlowDefinition,
) -> None:
    context = BookingContext(
        "change-phone",
        state=BookingState.COLLECTING_PHONE,
        phone="07733582649",
        customer=Customer("07733582649", "Lam"),
        phone_confirmed=True,
    )

    transition = StateMachine(flow).resolve_transition(context, "provide_phone")

    assert transition.target is BookingState.AWAITING_CONFIRMATION
    assert transition.actions == ("handle_phone_collection", "validate_phone")


def test_new_customer_name_submission_goes_straight_to_confirmation(
    flow: FlowDefinition,
) -> None:
    transition = _transition(flow, BookingState.COLLECTING_NAME, "provide_name")

    assert transition.target is BookingState.AWAITING_CONFIRMATION
    assert transition.actions == ("handle_customer_name",)


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


@pytest.mark.parametrize("intent", ["select_therapist", "deny"])
def test_therapist_step_returns_to_confirmation_when_phone_already_confirmed(
    flow: FlowDefinition,
    intent: str,
) -> None:
    context = BookingContext(
        conversation_id="change-time-conversation",
        state=BookingState.SELECTING_THERAPIST,
        customer=Customer(phone="0773582641", name="Duy"),
        phone="0773582641",
        phone_confirmed=True,
    )

    transition = StateMachine(flow).resolve_transition(context, intent)

    assert transition.target is BookingState.AWAITING_CONFIRMATION


def test_service_selection_owns_addons_and_slot_loading(
    flow: FlowDefinition,
) -> None:
    transitions = tuple(
        item
        for item in flow.states[BookingState.SELECTING_SERVICE].transitions
        if item.intent == "select_course"
    )

    assert len(transitions) == 2
    assert transitions[0].target is BookingState.SELECTING_SERVICE
    assert transitions[0].actions == ("handle_course_selection",)
    assert transitions[1].target is BookingState.SELECTING_TIME
    assert transitions[1].actions == ("handle_course_selection", "load_time_slots")


def test_service_failure_contract_is_complete(flow: FlowDefinition) -> None:
    transition = tuple(
        item
        for item in flow.states[BookingState.SELECTING_SERVICE].transitions
        if item.intent == "select_course"
    )[1]
    failures = {failure.condition: failure for failure in transition.on_fail}

    assert set(failures) == {
        "course_not_found",
        "main_course_missing",
        "addon_without_main_course",
        "combo_not_bookable",
        "course_duration_mismatch",
        "no_working_shift",
        "no_slots_available",
        "slot_api_error",
    }
    assert failures["combo_not_bookable"].actions == ("clear_course_for_reselect",)
    assert failures["course_duration_mismatch"].target is (BookingState.SELECTING_DURATION)
    assert failures["no_working_shift"].target is BookingState.SELECTING_DATE
    assert failures["no_slots_available"].target is BookingState.SELECTING_DATE
    assert failures["no_slots_available"].actions == ()


def test_duration_step_accepts_course_without_loading_slots(
    flow: FlowDefinition,
) -> None:
    transition = _transition(flow, BookingState.SELECTING_DURATION, "select_course")

    assert transition.target is BookingState.SELECTING_SERVICE
    assert transition.actions == (
        "handle_course_selection",
        "infer_duration_from_course",
    )
    assert "load_time_slots" not in transition.actions
    assert {failure.condition for failure in transition.on_fail} == {
        "invalid_duration",
        "course_not_found",
        "addon_without_main_course",
    }


def test_shop_selection_does_not_preload_an_unconsumed_catalog(
    flow: FlowDefinition,
) -> None:
    transition = _transition(flow, BookingState.SELECTING_SHOP, "select_store")

    assert transition.actions == ("handle_store_selection",)
    assert "load_service_catalog" not in _all_declared_actions(flow)


def test_date_selection_defers_availability_until_booking_shape_is_complete(
    flow: FlowDefinition,
) -> None:
    transition = _transition(flow, BookingState.SELECTING_DATE, "select_date")

    assert transition.actions == ("handle_date_selection",)
    assert "early_availability_check" not in _all_declared_actions(flow)


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
    assert unavailable.actions == ()
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


def test_phone_change_handler_returns_to_collection_from_confirmation(flow: FlowDefinition) -> None:
    rules = FlowLoader.load_change_handlers(CHANGE_HANDLERS_PATH)

    assert rules["phone"].next_state is BookingState.COLLECTING_PHONE
    assert rules["phone"].applied_state is BookingState.AWAITING_CONFIRMATION


def test_booking_failure_and_retry_paths(flow: FlowDefinition) -> None:
    failure = _transition(
        flow,
        BookingState.BOOKING_EXECUTING,
        "booking_failed",
    )
    retry = _transition(flow, BookingState.BOOKING_FAILED, "confirm")

    assert failure.target is BookingState.BOOKING_FAILED
    assert retry.target is BookingState.BOOKING_EXECUTING
    assert retry.actions == ()


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
def test_conversational_states_have_unknown_and_last_wildcard_without_faq(
    flow: FlowDefinition,
    state: BookingState,
) -> None:
    intents = tuple(item.intent for item in flow.states[state].transitions)
    unknown = _transition(flow, state, "unknown")
    wildcard = flow.states[state].transitions[-1]

    assert "ask_question" not in intents
    assert "unknown" in intents
    assert unknown.target is state
    assert unknown.actions == ("ask_to_clarify",)
    assert wildcard.intent == "*"
    assert wildcard.target is state
    assert wildcard.actions == ("log_unhandled", "ask_to_clarify")


def test_flow_has_no_out_of_flow_faq_action(flow: FlowDefinition) -> None:
    actions = {
        action
        for state in flow.states.values()
        for transition in state.transitions
        for action in transition.actions
    }

    assert "answer_question" not in actions


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


def test_action_registry_audits_declared_actions_without_reading_json(
    flow: FlowDefinition,
) -> None:
    bridge = ActionRegistry(
        search_shop_handler=cast(SearchShopHandler, object()),
        check_availability_handler=cast(CheckAvailabilityHandler, object()),
        check_customer_handler=cast(CheckCustomerHandler, object()),
        create_booking_handler=cast(CreateBookingHandler, object()),
        booking_gateway=cast(BookingGateway, object()),
    )
    declared_actions = _all_declared_actions(flow)
    unregistered = bridge.find_unregistered_actions(declared_actions)

    assert len(set(declared_actions)) == 29
    assert {
        "search_shop",
        "load_time_slots",
        "reload_time_slots",
        "handle_phone_collection",
        "create_booking",
        "lookup_existing_booking_for_cancel",
        "cancel_existing_booking",
    }.isdisjoint(unregistered)
    assert "run_final_check" not in declared_actions
    assert "complete_booking" not in declared_actions


def test_happy_path_actions_are_bound_with_explicit_non_runtime_allowlists(
    flow: FlowDefinition,
) -> None:
    bridge = ActionRegistry(
        search_shop_handler=cast(SearchShopHandler, object()),
        check_availability_handler=cast(CheckAvailabilityHandler, object()),
        check_customer_handler=cast(CheckCustomerHandler, object()),
        create_booking_handler=cast(CreateBookingHandler, object()),
        booking_gateway=cast(BookingGateway, object()),
    )
    happy_path_steps = (
        (BookingState.IDLE, "start_booking"),
        (BookingState.SELECTING_SHOP, "select_store"),
        (BookingState.SELECTING_DATE, "select_date"),
        (BookingState.SELECTING_PEOPLE, "select_people"),
        (BookingState.SELECTING_DURATION, "select_duration"),
        (BookingState.SELECTING_SERVICE, "select_course"),
    )
    happy_path_actions = tuple(
        action
        for state, intent in happy_path_steps
        for action in _transition(flow, state, intent).actions
    )
    dynamic_or_declarative = {
        "ask_to_clarify",
        "defer_change_info",
        "log_unhandled",
    }
    known_out_of_scope = {
        "ask_date",
        "ask_people",
        "clear_course_for_reselect",
        "handle_booking_failure",
        "infer_duration_from_course",
        "no_slots_available",
        "people_too_many",
    }

    assert bridge.find_unregistered_actions(happy_path_actions) == ()
    assert set(bridge.find_unregistered_actions(_all_declared_actions(flow))) <= (
        dynamic_or_declarative | known_out_of_scope
    )


def test_flow_failure_metadata_is_safe_and_resolvable(
    flow: FlowDefinition,
) -> None:
    failures = _all_failures(flow)

    assert failures
    assert all(failure.target in flow.states for failure in failures)
    assert all(
        failure.instruction_template is None or bool(failure.instruction_template.strip())
        for failure in failures
    )
    assert all("create_booking" not in failure.actions for failure in failures)

    for state in flow.states.values():
        on_enter_codes = tuple(failure.condition for failure in state.on_enter.on_fail)
        assert len(on_enter_codes) == len(set(on_enter_codes))
        for transition in state.transitions:
            codes = tuple(failure.condition for failure in transition.on_fail)
            assert len(codes) == len(set(codes))
        for auto_transition in state.auto_transitions:
            codes = tuple(failure.condition for failure in auto_transition.on_fail)
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
    mapped = set(ActionRegistry().mapped_failure_codes())

    assert {
        "invalid_phone",
        "customer_ng_blocked",
        "customer_verification_mismatch",
        "booking_api_error",
        "slot_api_error",
        "slot_unavailable",
        "course_duration_mismatch",
        "cancel_booking_identity_missing",
        "cancel_booking_not_found",
        "cancel_booking_already_cancelled",
    }.issubset(declared)
    assert {
        "invalid_phone",
        "customer_ng_blocked",
        "customer_verification_mismatch",
        "booking_api_error",
        "slot_api_error",
        "course_duration_mismatch",
        "cancel_booking_identity_missing",
        "cancel_booking_not_found",
        "cancel_booking_already_cancelled",
        "cancel_booking_unavailable",
    }.issubset(mapped)
    assert "course_not_found" in declared - mapped
    assert "booking_conflict" in mapped & declared


def test_booking_on_enter_failure_routing_is_declared(
    flow: FlowDefinition,
) -> None:
    executing = flow.states[BookingState.BOOKING_EXECUTING]
    failures = {failure.condition: failure for failure in executing.on_enter.on_fail}

    assert executing.on_enter.actions == ("create_booking",)
    assert failures["booking_conflict"].target is BookingState.SELECTING_TIME
    assert failures["booking_api_error"].target is BookingState.BOOKING_FAILED
    assert failures["booking_data_incomplete"].target is (BookingState.AWAITING_CONFIRMATION)
    assert failures["*"].target is BookingState.BOOKING_FAILED
    assert all(failure.actions == () for failure in failures.values())
