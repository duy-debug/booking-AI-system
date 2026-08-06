"""Tests for conditional declarative transition resolution."""

from datetime import time
from decimal import Decimal
from uuid import UUID

import pytest

from app.dialog.flow_loader import (
    FlowAutoTransition,
    FlowCondition,
    FlowDefinition,
    FlowFailure,
    FlowOnEnter,
    FlowState,
    FlowTransition,
    PhoneSplitConfig,
)
from app.dialog.state_machine import InvalidFlowConditionError, StateMachine
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    Course,
    InvalidBookingStateError,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState

SHOP = Shop(UUID("11111111-1111-1111-1111-111111111111"), "Central Spa")
COURSE = Course(
    UUID("22222222-2222-2222-2222-222222222222"),
    "Aromatherapy",
    60,
    Decimal("500000.00"),
)


def make_context(
    *,
    state: BookingState = BookingState.IDLE,
    **values: object,
) -> BookingContext:
    context = BookingContext(conversation_id="conversation-1", state=state)
    for field, value in values.items():
        setattr(context, field, value)
    return context


def make_flow(
    *,
    transitions: tuple[FlowTransition, ...] = (),
    auto_transitions: tuple[FlowAutoTransition, ...] = (),
    state: BookingState = BookingState.IDLE,
    terminal: bool = False,
) -> FlowDefinition:
    return FlowDefinition(
        version="2.0",
        name="test",
        description=None,
        initial_state=state,
        states={
            state: FlowState(
                description=None,
                on_enter=FlowOnEnter("instruction"),
                transitions=transitions,
                auto_transitions=auto_transitions,
                phone_split_mode=PhoneSplitConfig(3, 3, 5000),
                terminal=terminal,
            )
        },
    )


def machine_for_condition(condition: FlowCondition) -> StateMachine:
    transition = FlowTransition(
        "event",
        BookingState.COMPLETED,
        conditions=(condition,),
    )
    return StateMachine(make_flow(transitions=(transition,)))


def evaluate(condition: FlowCondition, context: BookingContext) -> bool:
    return machine_for_condition(condition)._evaluate_condition(condition, context)


def test_resolve_field_supports_direct_and_nested_paths() -> None:
    context = make_context(shop=SHOP, main_course=COURSE)
    machine = StateMachine(make_flow())

    assert machine._resolve_field(context, "shop") is SHOP
    assert machine._resolve_field(context, "shop.shop_id") == SHOP.shop_id
    assert machine._resolve_field(context, "main_course.course_id") == COURSE.course_id


def test_resolve_field_returns_none_for_missing_or_none_intermediate() -> None:
    context = make_context(shop=None)
    machine = StateMachine(make_flow())

    assert machine._resolve_field(context, "missing") is None
    assert machine._resolve_field(context, "shop.shop_id") is None


@pytest.mark.parametrize("field_path", ["", "shop..shop_id", "_private", "shop._id"])
def test_resolve_field_rejects_invalid_or_private_paths(field_path: str) -> None:
    with pytest.raises(InvalidFlowConditionError):
        StateMachine(make_flow())._resolve_field(make_context(), field_path)


@pytest.mark.parametrize(
    ("condition", "context"),
    [
        (
            FlowCondition("last_failure_code", "eq", "change"),
            make_context(last_failure_code="change"),
        ),
        (FlowCondition("num_customer", "eq", 2), make_context(num_customer=2)),
        (FlowCondition("phone_confirmed", "eq", True), make_context(phone_confirmed=True)),
        (
            FlowCondition(
                "therapist_preference.preference_type",
                "eq",
                "female",
            ),
            make_context(therapist_preference=TherapistPreference(TherapistPreferenceType.FEMALE)),
        ),
    ],
)
def test_eq_matches_strings_integers_booleans_and_enum_values(
    condition: FlowCondition,
    context: BookingContext,
) -> None:
    assert evaluate(condition, context) is True


def test_eq_returns_false_for_mismatch_and_missing_field() -> None:
    context = make_context(num_customer=1)

    assert evaluate(FlowCondition("num_customer", "eq", 2), context) is False
    assert evaluate(FlowCondition("missing", "eq", None), context) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phone_confirmed", False),
        ("num_customer", 0),
        ("last_failure_code", ""),
        ("available_slots", ()),
    ],
)
def test_not_null_does_not_use_truthiness(field: str, value: object) -> None:
    context = make_context()
    setattr(context, field, value)

    assert evaluate(FlowCondition(field, "not_null"), context) is True
    assert evaluate(FlowCondition(field, "null"), context) is False


def test_null_and_not_null_handle_none() -> None:
    context = make_context(phone=None)

    assert evaluate(FlowCondition("phone", "null"), context) is True
    assert evaluate(FlowCondition("phone", "not_null"), context) is False
    assert evaluate(FlowCondition("missing", "null"), context) is True


@pytest.mark.parametrize(
    ("condition", "context", "expected"),
    [
        (FlowCondition("num_customer", "gte", 2), make_context(num_customer=3), True),
        (FlowCondition("num_customer", "gte", 2), make_context(num_customer=2), True),
        (FlowCondition("num_customer", "gte", 2), make_context(num_customer=1), False),
        (FlowCondition("num_customer", "lte", 2), make_context(num_customer=1), True),
        (FlowCondition("num_customer", "lte", 2), make_context(num_customer=2), True),
        (FlowCondition("num_customer", "lte", 2), make_context(num_customer=3), False),
        (FlowCondition("num_customer", "gte", 2), make_context(num_customer=None), False),
        (
            FlowCondition("last_failure_code", "gte", 2),
            make_context(last_failure_code="invalid"),
            False,
        ),
    ],
)
def test_ordering_operators_are_safe(
    condition: FlowCondition,
    context: BookingContext,
    expected: bool,
) -> None:
    assert evaluate(condition, context) is expected


def test_in_supports_value_collection_and_enum_normalization() -> None:
    context = make_context(
        state=BookingState.SELECTING_SHOP,
        therapist_preference=TherapistPreference(TherapistPreferenceType.NONE),
    )

    assert evaluate(
        FlowCondition("state", "in", ("idle", "selecting_shop")),
        context,
    )
    assert evaluate(
        FlowCondition(
            "therapist_preference.preference_type",
            "in",
            ["none", "female"],
        ),
        context,
    )
    assert not evaluate(
        FlowCondition("state", "in", ("completed",)),
        context,
    )


def test_in_supports_reference_collection() -> None:
    selected = time(10, 30)
    context = make_context(start_time=selected, available_slots=(selected, time(11, 0)))

    assert evaluate(
        FlowCondition("start_time", "in", ref="available_slots"),
        context,
    )


@pytest.mark.parametrize(
    ("ref", "value"),
    [
        ("missing", None),
        ("available_slots", None),
        ("last_failure_code", "not-a-collection"),
    ],
)
def test_in_returns_false_for_invalid_runtime_reference(
    ref: str,
    value: object,
) -> None:
    context = make_context()
    if ref != "missing":
        setattr(context, ref, value)

    assert evaluate(FlowCondition("start_time", "in", ref=ref), context) is False


@pytest.mark.parametrize(
    "condition",
    [
        FlowCondition("start_time", "in"),
        FlowCondition("start_time", "in", (time(10, 30),), "available_slots"),
    ],
)
def test_in_requires_exactly_one_collection_source(
    condition: FlowCondition,
) -> None:
    with pytest.raises(InvalidFlowConditionError):
        evaluate(condition, make_context(start_time=time(10, 30)))


def test_nested_and_or_conditions() -> None:
    has_group = FlowCondition("num_customer", "gte", 2)
    phone_confirmed = FlowCondition("phone_confirmed", "eq", True)
    is_allowed = FlowCondition("is_ng_customer", "eq", False)
    context = make_context(
        num_customer=2,
        phone_confirmed=False,
        is_ng_customer=False,
    )

    assert evaluate(
        FlowCondition(
            op="and",
            conditions=(
                has_group,
                FlowCondition(
                    op="or",
                    conditions=(phone_confirmed, is_allowed),
                ),
            ),
        ),
        context,
    )
    assert not evaluate(
        FlowCondition(
            op="or",
            conditions=(
                FlowCondition(
                    op="and",
                    conditions=(has_group, phone_confirmed),
                ),
                FlowCondition("is_ng_customer", "eq", True),
            ),
        ),
        context,
    )


@pytest.mark.parametrize(
    "condition",
    [
        FlowCondition(op="and"),
        FlowCondition(op="or"),
        FlowCondition(field="phone", op="and", conditions=(FlowCondition("phone", "null"),)),
        FlowCondition(field=None, op="eq", value=True),
        FlowCondition(field="phone", op="unsupported"),
    ],
)
def test_invalid_condition_configuration_is_rejected(
    condition: FlowCondition,
) -> None:
    with pytest.raises(InvalidFlowConditionError):
        evaluate(condition, make_context())


def duplicate_intent_flow() -> FlowDefinition:
    transitions = (
        FlowTransition(
            "deny",
            BookingState.SELECTING_THERAPIST,
            conditions=(FlowCondition("last_failure_code", "eq", "therapist"),),
        ),
        FlowTransition(
            "deny",
            BookingState.SELECTING_TIME,
            conditions=(FlowCondition("last_failure_code", "eq", "time"),),
        ),
        FlowTransition("deny", BookingState.CANCELLED),
        FlowTransition("*", BookingState.IDLE),
    )
    return make_flow(transitions=transitions)


@pytest.mark.parametrize(
    ("last_failure_code", "target"),
    [
        ("therapist", BookingState.SELECTING_THERAPIST),
        ("time", BookingState.SELECTING_TIME),
        ("other", BookingState.CANCELLED),
    ],
)
def test_duplicate_intent_prefers_matching_condition_then_unconditional(
    last_failure_code: str,
    target: BookingState,
) -> None:
    context = make_context(last_failure_code=last_failure_code)

    transition = StateMachine(duplicate_intent_flow()).resolve_transition(
        context,
        "deny",
    )

    assert transition.target is target


def test_top_level_conditions_use_and_semantics() -> None:
    conditional = FlowTransition(
        "confirm",
        BookingState.COMPLETED,
        conditions=(
            FlowCondition("phone_confirmed", "eq", True),
            FlowCondition("ng_list_checked", "eq", True),
        ),
    )
    fallback = FlowTransition("confirm", BookingState.CANCELLED)
    machine = StateMachine(make_flow(transitions=(conditional, fallback)))

    assert (
        machine.resolve_transition(
            make_context(phone_confirmed=True, ng_list_checked=False),
            "confirm",
        ).target
        is BookingState.CANCELLED
    )


def test_exact_and_wildcard_resolution_order() -> None:
    transitions = (
        FlowTransition(
            "confirm",
            BookingState.COMPLETED,
            conditions=(FlowCondition("phone_confirmed", "eq", True),),
        ),
        FlowTransition(
            "*",
            BookingState.SELECTING_TIME,
            conditions=(FlowCondition("last_failure_code", "eq", "recover"),),
        ),
        FlowTransition("*", BookingState.IDLE),
    )
    machine = StateMachine(make_flow(transitions=transitions))

    assert (
        machine.resolve_transition(
            make_context(phone_confirmed=True),
            "confirm",
        ).target
        is BookingState.COMPLETED
    )
    assert (
        machine.resolve_transition(
            make_context(phone_confirmed=False, last_failure_code="recover"),
            "confirm",
        ).target
        is BookingState.SELECTING_TIME
    )
    assert machine.resolve_transition(make_context(), "unknown").target is BookingState.IDLE


def test_missing_transition_raises() -> None:
    with pytest.raises(InvalidBookingStateError):
        StateMachine(make_flow()).resolve_transition(make_context(), "unknown")


def test_auto_transition_returns_first_match_without_mutation_or_action_execution() -> None:
    first = FlowAutoTransition(
        FlowCondition("num_customer", "gte", 3),
        BookingState.CANCELLED,
        ("must_not_run",),
    )
    second = FlowAutoTransition(
        FlowCondition("num_customer", "gte", 2),
        BookingState.COLLECTING_PHONE,
        ("skip_therapist_for_group",),
    )
    context = make_context(
        state=BookingState.SELECTING_THERAPIST,
        num_customer=2,
        last_failure_code="keep",
    )
    machine = StateMachine(
        make_flow(
            state=BookingState.SELECTING_THERAPIST,
            auto_transitions=(first, second),
        )
    )

    resolved = machine.resolve_auto_transition(context)

    assert resolved is second
    assert resolved.actions == ("skip_therapist_for_group",)
    assert context.state is BookingState.SELECTING_THERAPIST
    assert context.last_failure_code == "keep"


def test_auto_transition_returns_none_when_no_condition_matches() -> None:
    auto = FlowAutoTransition(
        FlowCondition("num_customer", "gte", 2),
        BookingState.COLLECTING_PHONE,
    )
    machine = StateMachine(make_flow(auto_transitions=(auto,)))

    assert machine.resolve_auto_transition(make_context(num_customer=1)) is None


def test_auto_transition_uses_first_match_and_apply_commits_its_target() -> None:
    first = FlowAutoTransition(
        FlowCondition("num_customer", "gte", 2),
        BookingState.COLLECTING_PHONE,
    )
    second = FlowAutoTransition(
        FlowCondition("num_customer", "gte", 2),
        BookingState.VERIFYING_PHONE,
    )
    machine = StateMachine(make_flow(auto_transitions=(first, second)))
    context = make_context(num_customer=2)

    resolved = machine.resolve_auto_transition(context)

    assert resolved is first
    assert context.state is BookingState.IDLE
    machine.apply_transition(context, resolved)
    assert context.state is BookingState.COLLECTING_PHONE


def test_resolve_and_transition_alias_do_not_apply_until_explicit_commit() -> None:
    configured = FlowTransition(
        "start",
        BookingState.SELECTING_SHOP,
        ("search_shop",),
    )
    machine = StateMachine(make_flow(transitions=(configured,)))
    context = make_context()

    resolved = machine.resolve_transition(context, "start")
    alias_result = machine.transition(context, "start")

    assert resolved is configured
    assert alias_result is configured
    assert context.state is BookingState.IDLE
    machine.apply_transition(context, resolved)
    assert context.state is BookingState.SELECTING_SHOP


def test_can_transition_respects_conditions_and_does_not_mutate() -> None:
    configured = FlowTransition(
        "confirm",
        BookingState.COMPLETED,
        conditions=(FlowCondition("phone_confirmed", "eq", True),),
    )
    machine = StateMachine(make_flow(transitions=(configured,)))
    context = make_context(phone_confirmed=False)

    assert machine.can_transition(context, "confirm") is False
    assert context.state is BookingState.IDLE


def test_can_transition_does_not_hide_invalid_condition_configuration() -> None:
    configured = FlowTransition(
        "confirm",
        BookingState.COMPLETED,
        conditions=(FlowCondition(op="and"),),
    )

    with pytest.raises(InvalidFlowConditionError):
        StateMachine(make_flow(transitions=(configured,))).can_transition(
            make_context(),
            "confirm",
        )


def test_available_events_deduplicates_in_first_seen_order() -> None:
    machine = StateMachine(duplicate_intent_flow())

    assert machine.available_events(BookingState.IDLE) == ("deny", "*")


def test_terminal_state_rejects_events_and_has_no_auto_resolution() -> None:
    auto = FlowAutoTransition(
        FlowCondition("booking", "not_null"),
        BookingState.COMPLETED,
    )
    machine = StateMachine(
        make_flow(
            state=BookingState.COMPLETED,
            auto_transitions=(auto,),
            terminal=True,
        )
    )
    context = make_context(state=BookingState.COMPLETED)

    with pytest.raises(InvalidBookingStateError):
        machine.resolve_transition(context, "anything")
    assert machine.resolve_auto_transition(context) is None


def test_get_configuration_helpers_and_unknown_state() -> None:
    machine = StateMachine(make_flow())

    assert machine.get_auto_transitions(BookingState.IDLE) == ()
    assert machine.get_phone_split_config(BookingState.IDLE) == PhoneSplitConfig(
        3,
        3,
        5000,
    )
    with pytest.raises(InvalidBookingStateError):
        machine.get_state_definition(BookingState.COMPLETED)


def test_resolve_failure_prefers_exact_code_before_fallback() -> None:
    exact = FlowFailure(
        "slot_unavailable",
        BookingState.SELECTING_TIME,
        ("suggest_nearest_time",),
        "slot_unavailable",
    )
    fallback = FlowFailure(
        "*",
        BookingState.SELECTING_SERVICE,
        instruction_template="ask_course",
    )
    transition = FlowTransition(
        "select_time",
        BookingState.SELECTING_THERAPIST,
        on_fail=(fallback, exact),
    )

    resolved = StateMachine(make_flow()).resolve_failure(
        transition,
        "slot_unavailable",
    )

    assert resolved is exact
    assert resolved.actions == ("suggest_nearest_time",)
    assert resolved.instruction_template == "slot_unavailable"


def test_resolve_failure_uses_wildcard_then_default_fallback() -> None:
    wildcard = FlowFailure("*", BookingState.SELECTING_TIME)
    default = FlowFailure("default", BookingState.SELECTING_SERVICE)
    machine = StateMachine(make_flow())

    assert (
        machine.resolve_failure(
            FlowTransition(
                "select_time",
                BookingState.SELECTING_THERAPIST,
                on_fail=(default, wildcard),
            ),
            "unmapped",
        )
        is wildcard
    )
    assert (
        machine.resolve_failure(
            FlowTransition(
                "select_time",
                BookingState.SELECTING_THERAPIST,
                on_fail=(default,),
            ),
            "unmapped",
        )
        is default
    )


def test_resolve_failure_returns_none_without_match_or_fallback() -> None:
    transition = FlowTransition(
        "select_time",
        BookingState.SELECTING_THERAPIST,
        on_fail=(FlowFailure("slot_unavailable", BookingState.SELECTING_TIME),),
    )

    assert StateMachine(make_flow()).resolve_failure(transition, "booking_api_error") is None


def test_resolve_failure_does_not_mutate_until_apply_failure() -> None:
    context = make_context(state=BookingState.SELECTING_SERVICE)
    failure = FlowFailure(
        "course_duration_mismatch",
        BookingState.SELECTING_DURATION,
    )
    transition = FlowTransition(
        "select_course",
        BookingState.SELECTING_TIME,
        on_fail=(failure,),
    )
    machine = StateMachine(make_flow())

    resolved = machine.resolve_failure(
        transition,
        "course_duration_mismatch",
    )

    assert resolved is failure
    assert context.state is BookingState.SELECTING_SERVICE
    machine.apply_failure(context, resolved)
    assert context.state is BookingState.SELECTING_DURATION


def test_failure_code_is_not_evaluated_as_flow_condition() -> None:
    failure = FlowFailure("gte", BookingState.SELECTING_TIME)
    transition = FlowTransition(
        "select_time",
        BookingState.SELECTING_THERAPIST,
        on_fail=(failure,),
    )

    assert StateMachine(make_flow()).resolve_failure(transition, "gte") is failure


def test_resolve_failure_supports_flow_on_enter_without_mutation() -> None:
    context = make_context(state=BookingState.BOOKING_EXECUTING)
    exact = FlowFailure(
        "booking_conflict",
        BookingState.SELECTING_TIME,
        instruction_template="slot_unavailable",
    )
    wildcard = FlowFailure(
        "*",
        BookingState.BOOKING_FAILED,
        instruction_template="booking_failed",
    )
    on_enter = FlowOnEnter(
        "booking_processing",
        ("create_booking",),
        (wildcard, exact),
    )
    machine = StateMachine(make_flow())

    assert machine.resolve_failure(on_enter, "booking_conflict") is exact
    assert machine.resolve_failure(on_enter, "unknown_failure") is wildcard
    assert context.state is BookingState.BOOKING_EXECUTING


def test_flow_on_enter_failure_returns_none_without_route() -> None:
    on_enter = FlowOnEnter("instruction", ("action",))

    assert StateMachine(make_flow()).resolve_failure(on_enter, "booking_api_error") is None
