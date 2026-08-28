"""Tests for parsed-turn dialog workflow orchestration."""

from datetime import date, time
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

from app.application.action_registry import (
    ActionCallable,
    ActionExecutionContext,
    ActionRegistry,
    ActionResult,
)
from app.dialog.dialog_controller import (
    DialogController,
    DialogTurnInput,
    DialogTurnStatus,
    InvalidDialogTurnError,
    _stage_requested_entities,
)
from app.dialog.flow_loader import (
    ChangeRule,
    FlowAutoTransition,
    FlowCondition,
    FlowDefinition,
    FlowFailure,
    FlowOnEnter,
    FlowState,
    FlowTransition,
)
from app.dialog.nlu import NLUResolutionStatus, NLUResult, NLUSource
from app.dialog.state_machine import StateMachine
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    Booking,
    Course,
    CourseSelection,
    CourseType,
    Shop,
    SlotConflictError,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState


def state(
    *,
    transitions: tuple[FlowTransition, ...] = (),
    on_enter: FlowOnEnter | None = None,
    auto_transitions: tuple[FlowAutoTransition, ...] = (),
    terminal: bool = False,
) -> FlowState:
    return FlowState(
        description=None,
        on_enter=on_enter or FlowOnEnter(),
        transitions=transitions,
        auto_transitions=auto_transitions,
        terminal=terminal,
    )


def flow_for(states: dict[BookingState, FlowState]) -> FlowDefinition:
    return FlowDefinition(
        version="test",
        name="controller-test",
        description=None,
        initial_state=BookingState.IDLE,
        states=states,
    )


def controller(
    flow: FlowDefinition,
    bridge: ActionRegistry,
    *,
    change_rules: dict[str, ChangeRule] | None = None,
    max_auto_transitions: int = 8,
) -> DialogController:
    return DialogController(
        flow=flow,
        state_machine=StateMachine(flow),
        action_registry=bridge,
        change_rules=change_rules,
        max_auto_transitions=max_auto_transitions,
    )


def recording_action(
    name: str,
    calls: list[str],
) -> ActionCallable:
    async def execute(context: ActionExecutionContext) -> ActionResult:
        calls.append(name)
        return ActionResult(name)

    return execute


def sample_shop() -> Shop:
    return Shop(
        shop_id=UUID("00000000-0000-0000-0000-000000000001"),
        name="Komorebi Test",
    )


def main_course(
    suffix: str,
    *,
    duration_minutes: int = 60,
) -> Course:
    return Course(
        course_id=UUID(f"00000000-0000-0000-0000-0000000000{suffix}"),
        name=f"Course {suffix}",
        duration_minutes=duration_minutes,
        price=Decimal("100000"),
        course_type=CourseType.MAIN,
    )


def test_turn_input_validates_intent_and_copies_payload() -> None:
    payload: dict[str, object] = {"value": 1}
    turn = DialogTurnInput("go", payload)
    payload["value"] = 2

    assert turn.payload["value"] == 1
    with pytest.raises(TypeError):
        cast(dict[str, object], turn.payload)["other"] = 3
    with pytest.raises(InvalidDialogTurnError):
        DialogTurnInput(" ", {})


def test_controller_rejects_invalid_auto_transition_limit() -> None:
    flow = flow_for({BookingState.IDLE: state()})

    with pytest.raises(ValueError):
        controller(flow, ActionRegistry(), max_auto_transitions=0)


def test_stage_requested_entities_preserves_secondary_start_time_until_time_step() -> None:
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_PEOPLE,
        requested_booking_date=date(2026, 8, 10),
    )
    result = NLUResult(
        intent="select_people",
        payload={"num_customer": 1},
        confidence=0.99,
        source=NLUSource.LLM,
        resolution_status=NLUResolutionStatus.RESOLVED,
        merged_entities={
            "number_of_people": 1,
            "start_time": time(8, 0),
        },
    )

    _stage_requested_entities(result, context)

    assert context.requested_num_customer is None
    assert context.requested_start_time == time(8, 0)


@pytest.mark.asyncio
async def test_success_executes_transition_on_enter_and_auto_in_order() -> None:
    calls: list[str] = []
    bridge = ActionRegistry()
    for name in (
        "transition_action",
        "target_enter_action",
        "auto_action",
        "auto_target_enter_action",
    ):
        bridge.register_action(name, recording_action(name, calls))
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(
                    FlowTransition(
                        "go",
                        BookingState.SELECTING_SHOP,
                        ("transition_action",),
                    ),
                )
            ),
            BookingState.SELECTING_SHOP: state(
                on_enter=FlowOnEnter(
                    "ask_shop",
                    ("target_enter_action",),
                ),
                auto_transitions=(
                    FlowAutoTransition(
                        FlowCondition("num_customer", "gte", 2),
                        BookingState.SELECTING_DATE,
                        ("auto_action",),
                    ),
                ),
            ),
            BookingState.SELECTING_DATE: state(
                on_enter=FlowOnEnter(
                    "ask_date",
                    ("auto_target_enter_action",),
                )
            ),
        }
    )
    context = BookingContext(conversation_id="c-1", num_customer=2)

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.initial_state is BookingState.IDLE
    assert result.final_state is BookingState.SELECTING_DATE
    assert result.instruction_template == "ask_date"
    assert result.executed_actions == tuple(calls)
    assert result.auto_transition_count == 1
    assert calls == [
        "transition_action",
        "target_enter_action",
        "auto_action",
        "auto_target_enter_action",
    ]


@pytest.mark.asyncio
async def test_empty_transition_actions_apply_target_normally() -> None:
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(FlowTransition("go", BookingState.SELECTING_SHOP),)
            ),
            BookingState.SELECTING_SHOP: state(on_enter=FlowOnEnter("ask_shop")),
        }
    )
    context = BookingContext(conversation_id="c-1")

    result = await controller(flow, ActionRegistry()).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert context.state is BookingState.SELECTING_SHOP
    assert result.executed_actions == ()
    assert result.auto_transition_count == 0


@pytest.mark.asyncio
async def test_transition_target_is_not_applied_before_action_success() -> None:
    observed_states: list[BookingState] = []
    bridge = ActionRegistry()

    async def fail(context: ActionExecutionContext) -> ActionResult:
        observed_states.append(context.booking_context.state)
        raise RuntimeError("transition failed")

    bridge.register_action("failing_action", fail)
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(
                    FlowTransition(
                        "go",
                        BookingState.SELECTING_SHOP,
                        ("failing_action",),
                    ),
                )
            ),
            BookingState.SELECTING_SHOP: state(),
        }
    )
    context = BookingContext(conversation_id="c-1")

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert observed_states == [BookingState.IDLE]
    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert context.state is BookingState.IDLE


@pytest.mark.parametrize("use_wildcard", [False, True])
@pytest.mark.asyncio
async def test_transition_failure_uses_exact_or_wildcard_route(
    use_wildcard: bool,
) -> None:
    calls: list[str] = []
    bridge = ActionRegistry(failure_code_provider=lambda error: "typed_failure")

    async def fail(context: ActionExecutionContext) -> ActionResult:
        context.booking_context.phone = "rolled-back"
        raise RuntimeError("failure")

    bridge.register_action("failing_action", fail)
    bridge.register_action(
        "recovery_action",
        recording_action("recovery_action", calls),
    )
    bridge.register_action(
        "must_not_run",
        recording_action("must_not_run", calls),
    )
    condition = "*" if use_wildcard else "typed_failure"
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(
                    FlowTransition(
                        "go",
                        BookingState.SELECTING_SHOP,
                        ("failing_action",),
                        on_fail=(
                            FlowFailure(
                                condition,
                                BookingState.SELECTING_DATE,
                                ("recovery_action",),
                                "recovered",
                            ),
                        ),
                    ),
                )
            ),
            BookingState.SELECTING_SHOP: state(),
            BookingState.SELECTING_DATE: state(
                on_enter=FlowOnEnter("must_not_run", ("must_not_run",))
            ),
        }
    )
    context = BookingContext(conversation_id="c-1", phone="original")

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    assert result.failure_code == "typed_failure"
    assert result.instruction_template == "recovered"
    assert result.executed_actions == ("recovery_action",)
    assert result.original_error is not None
    assert context.phone == "original"
    assert context.state is BookingState.SELECTING_DATE
    assert calls == ["recovery_action"]


@pytest.mark.asyncio
async def test_failed_recovery_is_unhandled_and_does_not_apply_target() -> None:
    bridge = ActionRegistry(failure_code_provider=lambda error: "typed_failure")

    async def transition_failure(context: ActionExecutionContext) -> ActionResult:
        raise RuntimeError("transition failed")

    async def first_recovery(context: ActionExecutionContext) -> ActionResult:
        context.booking_context.phone = "mutated"
        return ActionResult("first_recovery")

    async def second_recovery(context: ActionExecutionContext) -> ActionResult:
        raise RuntimeError("recovery failed")

    bridge.register_action("transition_failure", transition_failure)
    bridge.register_action("first_recovery", first_recovery)
    bridge.register_action("second_recovery", second_recovery)
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(
                    FlowTransition(
                        "go",
                        BookingState.SELECTING_SHOP,
                        ("transition_failure",),
                        on_fail=(
                            FlowFailure(
                                "typed_failure",
                                BookingState.SELECTING_DATE,
                                ("first_recovery", "second_recovery"),
                            ),
                        ),
                    ),
                )
            ),
            BookingState.SELECTING_SHOP: state(),
            BookingState.SELECTING_DATE: state(),
        }
    )
    context = BookingContext(conversation_id="c-1", phone="original")

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert result.original_error is not None
    assert result.failed_action == "second_recovery"
    assert result.executed_actions == ()
    assert context.phone == "original"
    assert context.state is BookingState.IDLE


@pytest.mark.parametrize(
    ("cause", "expected_state", "expected_template", "expected_code"),
    [
        (
            SlotConflictError(),
            BookingState.SELECTING_TIME,
            "slot_unavailable",
            "booking_conflict",
        ),
        (
            RuntimeError("POS unavailable"),
            BookingState.BOOKING_FAILED,
            "booking_failed",
            "booking_api_error",
        ),
    ],
)
@pytest.mark.asyncio
async def test_on_enter_create_failure_uses_declarative_route(
    cause: Exception,
    expected_state: BookingState,
    expected_template: str,
    expected_code: str,
) -> None:
    create_calls = 0
    bridge = ActionRegistry()

    async def create(context: ActionExecutionContext) -> ActionResult:
        nonlocal create_calls
        create_calls += 1
        assert context.booking_context.state is BookingState.BOOKING_EXECUTING
        raise cause

    bridge.register_action("create_booking", create)
    on_fail = (
        FlowFailure(
            "booking_conflict",
            BookingState.SELECTING_TIME,
            instruction_template="slot_unavailable",
        ),
        FlowFailure(
            "booking_api_error",
            BookingState.BOOKING_FAILED,
            instruction_template="booking_failed",
        ),
    )
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("confirm", BookingState.BOOKING_EXECUTING),)
            ),
            BookingState.BOOKING_EXECUTING: state(
                on_enter=FlowOnEnter(
                    "booking_processing",
                    ("create_booking",),
                    on_fail,
                )
            ),
            BookingState.SELECTING_TIME: state(),
            BookingState.BOOKING_FAILED: state(),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
    )

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("confirm", {}, idempotency_key="stable-key"),
    )

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    assert result.failure_code == expected_code
    assert result.instruction_template == expected_template
    assert context.state is expected_state
    assert create_calls == 1


@pytest.mark.asyncio
async def test_unknown_on_enter_failure_keeps_applied_target() -> None:
    bridge = ActionRegistry()

    async def enter_failure(context: ActionExecutionContext) -> ActionResult:
        raise RuntimeError("unknown")

    bridge.register_action("enter_failure", enter_failure)
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(FlowTransition("go", BookingState.SELECTING_SHOP),)
            ),
            BookingState.SELECTING_SHOP: state(
                on_enter=FlowOnEnter("ask_shop", ("enter_failure",))
            ),
        }
    )
    context = BookingContext(conversation_id="c-1")

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert context.state is BookingState.SELECTING_SHOP
    assert result.instruction_template is None


@pytest.mark.asyncio
async def test_final_confirmation_generates_server_idempotency_before_create() -> None:
    bridge = ActionRegistry()
    calls = 0

    async def create(context: ActionExecutionContext) -> ActionResult:
        nonlocal calls
        calls += 1
        return ActionResult("create_booking")

    bridge.register_action("create_booking", create)
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("confirm", BookingState.BOOKING_EXECUTING),)
            ),
            BookingState.BOOKING_EXECUTING: state(
                on_enter=FlowOnEnter(
                    "booking_processing",
                    ("create_booking",),
                    (
                        FlowFailure(
                            "booking_data_incomplete",
                            BookingState.AWAITING_CONFIRMATION,
                            instruction_template="booking_data_incomplete",
                        ),
                    ),
                )
            ),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
    )

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("confirm", {}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.failure_code is None
    assert context.state is BookingState.BOOKING_EXECUTING
    assert context.booking_attempt_id is not None
    assert calls == 1


@pytest.mark.asyncio
async def test_booking_success_auto_completes_without_double_create() -> None:
    create_calls = 0
    bridge = ActionRegistry()

    async def create(context: ActionExecutionContext) -> ActionResult:
        nonlocal create_calls
        create_calls += 1
        context.booking_context.booking = cast(Booking, object())
        return ActionResult("create_booking")

    bridge.register_action("create_booking", create)
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("confirm", BookingState.BOOKING_EXECUTING),)
            ),
            BookingState.BOOKING_EXECUTING: state(
                on_enter=FlowOnEnter(
                    "booking_processing",
                    ("create_booking",),
                ),
                auto_transitions=(
                    FlowAutoTransition(
                        FlowCondition("booking", "not_null"),
                        BookingState.COMPLETED,
                    ),
                ),
            ),
            BookingState.COMPLETED: state(
                on_enter=FlowOnEnter("booking_complete"),
                terminal=True,
            ),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
    )

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("confirm", {}, idempotency_key="stable-key"),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.COMPLETED
    assert result.instruction_template == "booking_complete"
    assert result.auto_transition_count == 1
    assert result.executed_actions == ("create_booking",)
    assert create_calls == 1


@pytest.mark.asyncio
async def test_auto_action_failure_does_not_apply_auto_target() -> None:
    bridge = ActionRegistry()

    async def auto_failure(context: ActionExecutionContext) -> ActionResult:
        raise RuntimeError("auto failure")

    bridge.register_action("auto_failure", auto_failure)
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(FlowTransition("go", BookingState.SELECTING_THERAPIST),)
            ),
            BookingState.SELECTING_THERAPIST: state(
                auto_transitions=(
                    FlowAutoTransition(
                        FlowCondition("num_customer", "gte", 2),
                        BookingState.COLLECTING_PHONE,
                        ("auto_failure",),
                    ),
                )
            ),
            BookingState.COLLECTING_PHONE: state(),
        }
    )
    context = BookingContext(conversation_id="c-1", num_customer=2)

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert result.auto_transition_count == 0
    assert context.state is BookingState.SELECTING_THERAPIST


@pytest.mark.asyncio
async def test_auto_action_failure_uses_its_own_failure_routes() -> None:
    bridge = ActionRegistry(failure_code_provider=lambda error: "auto_failed")

    async def auto_failure(context: ActionExecutionContext) -> ActionResult:
        raise RuntimeError("auto failure")

    bridge.register_action("auto_failure", auto_failure)
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(FlowTransition("go", BookingState.SELECTING_THERAPIST),)
            ),
            BookingState.SELECTING_THERAPIST: state(
                auto_transitions=(
                    FlowAutoTransition(
                        FlowCondition("num_customer", "gte", 2),
                        BookingState.COLLECTING_PHONE,
                        ("auto_failure",),
                        (
                            FlowFailure(
                                "auto_failed",
                                BookingState.SELECTING_TIME,
                                instruction_template="retry_time",
                            ),
                        ),
                    ),
                )
            ),
            BookingState.COLLECTING_PHONE: state(),
            BookingState.SELECTING_TIME: state(),
        }
    )
    context = BookingContext(conversation_id="c-1", num_customer=2)

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    assert result.failure_code == "auto_failed"
    assert result.instruction_template == "retry_time"
    assert result.auto_transition_count == 0
    assert context.state is BookingState.SELECTING_TIME


@pytest.mark.asyncio
async def test_group_booking_auto_skips_therapist_and_enters_phone_state() -> None:
    condition = FlowCondition("num_customer", "gte", 2)
    flow = flow_for(
        {
            BookingState.SELECTING_TIME: state(
                transitions=(
                    FlowTransition(
                        "select_time",
                        BookingState.SELECTING_THERAPIST,
                        ("handle_time_selection",),
                    ),
                )
            ),
            BookingState.SELECTING_THERAPIST: state(
                on_enter=FlowOnEnter("ask_therapist"),
                auto_transitions=(
                    FlowAutoTransition(
                        condition,
                        BookingState.COLLECTING_PHONE,
                        ("skip_therapist_for_group",),
                    ),
                ),
            ),
            BookingState.COLLECTING_PHONE: state(on_enter=FlowOnEnter("ask_phone")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.SELECTING_TIME,
        num_customer=2,
        available_slots=(time(10, 30),),
    )

    result = await controller(flow, ActionRegistry()).handle_turn(
        context,
        DialogTurnInput("select_time", {"start_time": time(10, 30)}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.COLLECTING_PHONE
    assert result.instruction_template == "ask_phone"
    assert result.auto_transition_count == 1
    assert result.executed_actions == (
        "handle_time_selection",
        "skip_therapist_for_group",
    )


@pytest.mark.asyncio
async def test_change_time_returns_to_confirmation_when_therapist_is_verified() -> None:
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("change_info", BookingState.AWAITING_CONFIRMATION),),
                on_enter=FlowOnEnter("final_confirmation"),
            ),
            BookingState.SELECTING_THERAPIST: state(on_enter=FlowOnEnter("ask_therapist")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
        num_customer=1,
        start_time=time(10, 30),
        therapist_preference=TherapistPreference(TherapistPreferenceType.NONE),
        therapist_verified=True,
        available_slots=(time(13, 0),),
    )

    result = await controller(
        flow,
        ActionRegistry(),
        change_rules={
            "time": ChangeRule(
                reset_action="change_time",
                next_state=BookingState.SELECTING_TIME,
                applied_state=BookingState.SELECTING_THERAPIST,
                prompt_template="change_ask_time",
            )
        },
    ).handle_turn(
        context,
        DialogTurnInput(
            "change_info",
            {"change_target": "time", "start_time": time(13, 0)},
        ),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.AWAITING_CONFIRMATION
    assert result.instruction_template == "final_confirmation"
    assert context.start_time == time(13, 0)
    assert context.therapist_verified is True


@pytest.mark.asyncio
async def test_change_time_asks_therapist_again_when_previous_one_is_unavailable() -> None:
    async def change_time_with_unavailable_therapist(
        action_context: ActionExecutionContext,
    ) -> ActionResult:
        action_context.booking_context.change_start_time(time(13, 0))
        action_context.booking_context.set_therapist_preference(None)
        action_context.booking_context.last_failure_code = "therapist_unavailable"
        return ActionResult("change_time")

    bridge = ActionRegistry()
    bridge._actions["change_time"] = change_time_with_unavailable_therapist
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("change_info", BookingState.AWAITING_CONFIRMATION),),
                on_enter=FlowOnEnter("final_confirmation"),
            ),
            BookingState.SELECTING_THERAPIST: state(on_enter=FlowOnEnter("ask_therapist")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
        num_customer=1,
        start_time=time(10, 30),
        therapist_verified=True,
        available_slots=(time(13, 0),),
    )

    result = await controller(
        flow,
        bridge,
        change_rules={
            "time": ChangeRule(
                reset_action="change_time",
                next_state=BookingState.SELECTING_TIME,
                applied_state=BookingState.SELECTING_THERAPIST,
                prompt_template="change_ask_time",
            )
        },
    ).handle_turn(
        context,
        DialogTurnInput(
            "change_info",
            {"change_target": "time", "start_time": time(13, 0)},
        ),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.SELECTING_THERAPIST
    assert result.instruction_template == "therapist_unavailable"
    assert context.start_time == time(13, 0)


@pytest.mark.asyncio
async def test_change_main_course_reloads_slots_and_keeps_valid_previous_time() -> None:
    old_course = main_course("01")
    new_course = main_course("02")

    async def change_course(action_context: ActionExecutionContext) -> ActionResult:
        action_context.booking_context.change_course_selection(CourseSelection(new_course))
        return ActionResult("change_course", CourseSelection(new_course))

    async def load_time_slots(action_context: ActionExecutionContext) -> ActionResult:
        slots = (time(10, 30), time(11, 0))
        action_context.booking_context.set_available_slots(slots)
        return ActionResult("load_time_slots", slots)

    bridge = ActionRegistry()
    bridge._actions["change_course"] = change_course
    bridge._actions["load_time_slots"] = load_time_slots
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("change_info", BookingState.AWAITING_CONFIRMATION),),
                on_enter=FlowOnEnter("final_confirmation"),
            ),
            BookingState.SELECTING_TIME: state(on_enter=FlowOnEnter("suggest_time_slots")),
            BookingState.SELECTING_DATE: state(on_enter=FlowOnEnter("ask_date")),
            BookingState.SELECTING_THERAPIST: state(on_enter=FlowOnEnter("ask_therapist")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=sample_shop(),
        booking_date=date(2026, 8, 27),
        num_customer=2,
        duration_minutes=60,
        main_course=old_course,
        start_time=time(10, 30),
        therapist_preference=TherapistPreference(TherapistPreferenceType.NONE),
        therapist_verified=True,
        available_slots=(time(10, 30),),
    )

    result = await controller(
        flow,
        bridge,
        change_rules={
            "main_course": ChangeRule(
                reset_action="change_course",
                next_state=BookingState.SELECTING_SERVICE,
                applied_state=BookingState.SELECTING_TIME,
                prompt_template="change_ask_course",
            )
        },
    ).handle_turn(
        context,
        DialogTurnInput(
            "change_info",
            {"change_target": "main_course", "course_selection": CourseSelection(new_course)},
        ),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.AWAITING_CONFIRMATION
    assert result.instruction_template == "final_confirmation"
    assert result.executed_actions == ("change_course", "load_time_slots", "change_time")
    assert context.main_course == new_course
    assert context.start_time == time(10, 30)
    assert context.therapist_preference == TherapistPreference(TherapistPreferenceType.NONE)
    assert context.therapist_verified is True


@pytest.mark.asyncio
async def test_change_main_course_reloads_slots_and_asks_time_when_previous_time_is_gone() -> None:
    old_course = main_course("03")
    new_course = main_course("04")

    async def change_course(action_context: ActionExecutionContext) -> ActionResult:
        action_context.booking_context.change_course_selection(CourseSelection(new_course))
        return ActionResult("change_course", CourseSelection(new_course))

    async def load_time_slots(action_context: ActionExecutionContext) -> ActionResult:
        slots = (time(11, 0), time(11, 30))
        action_context.booking_context.set_available_slots(slots)
        return ActionResult("load_time_slots", slots)

    bridge = ActionRegistry()
    bridge._actions["change_course"] = change_course
    bridge._actions["load_time_slots"] = load_time_slots
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("change_info", BookingState.AWAITING_CONFIRMATION),),
                on_enter=FlowOnEnter("final_confirmation"),
            ),
            BookingState.SELECTING_TIME: state(on_enter=FlowOnEnter("suggest_time_slots")),
            BookingState.SELECTING_DATE: state(on_enter=FlowOnEnter("ask_date")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=sample_shop(),
        booking_date=date(2026, 8, 27),
        num_customer=1,
        duration_minutes=60,
        main_course=old_course,
        start_time=time(10, 30),
        available_slots=(time(10, 30),),
    )

    result = await controller(
        flow,
        bridge,
        change_rules={
            "main_course": ChangeRule(
                reset_action="change_course",
                next_state=BookingState.SELECTING_SERVICE,
                applied_state=BookingState.SELECTING_TIME,
                prompt_template="change_ask_course",
            )
        },
    ).handle_turn(
        context,
        DialogTurnInput(
            "change_info",
            {"change_target": "main_course", "course_selection": CourseSelection(new_course)},
        ),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.SELECTING_TIME
    assert result.instruction_template == "suggest_time_slots"
    assert result.executed_actions == ("change_course", "load_time_slots")
    assert context.available_slots == (time(11, 0), time(11, 30))
    assert context.start_time is None


@pytest.mark.asyncio
async def test_change_main_course_slot_reload_failure_recovers_to_date_step() -> None:
    old_course = main_course("06")
    new_course = main_course("07")

    async def change_course(action_context: ActionExecutionContext) -> ActionResult:
        action_context.booking_context.change_course_selection(CourseSelection(new_course))
        return ActionResult("change_course", CourseSelection(new_course))

    async def load_time_slots(action_context: ActionExecutionContext) -> ActionResult:
        raise SlotConflictError(reason="no_slots_available")

    bridge = ActionRegistry()
    bridge._actions["change_course"] = change_course
    bridge._actions["load_time_slots"] = load_time_slots
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("change_info", BookingState.AWAITING_CONFIRMATION),),
                on_enter=FlowOnEnter("final_confirmation"),
            ),
            BookingState.SELECTING_TIME: state(on_enter=FlowOnEnter("suggest_time_slots")),
            BookingState.SELECTING_DATE: state(on_enter=FlowOnEnter("ask_date")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=sample_shop(),
        booking_date=date(2026, 8, 27),
        num_customer=1,
        duration_minutes=60,
        main_course=old_course,
        start_time=time(10, 30),
        available_slots=(time(10, 30),),
    )

    result = await controller(
        flow,
        bridge,
        change_rules={
            "main_course": ChangeRule(
                reset_action="change_course",
                next_state=BookingState.SELECTING_SERVICE,
                applied_state=BookingState.SELECTING_TIME,
                prompt_template="change_ask_course",
            )
        },
    ).handle_turn(
        context,
        DialogTurnInput(
            "change_info",
            {"change_target": "main_course", "course_selection": CourseSelection(new_course)},
        ),
    )

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    assert result.final_state is BookingState.SELECTING_DATE
    assert result.instruction_template == "no_slots_available"
    assert result.failure_code == "no_slots_available"
    assert result.executed_actions == ("change_course",)
    assert context.main_course == new_course
    assert context.start_time is None


@pytest.mark.asyncio
async def test_change_date_prompt_does_not_clear_existing_booking_details() -> None:
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("change_info", BookingState.AWAITING_CONFIRMATION),),
                on_enter=FlowOnEnter("final_confirmation"),
            ),
            BookingState.SELECTING_DATE: state(on_enter=FlowOnEnter("change_ask_date")),
        }
    )
    selected_course = main_course("08")
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=sample_shop(),
        booking_date=date(2026, 10, 29),
        num_customer=1,
        duration_minutes=60,
        main_course=selected_course,
        start_time=time(11, 0),
        therapist_preference=TherapistPreference(TherapistPreferenceType.NONE),
        therapist_verified=True,
        available_slots=(time(11, 0),),
    )

    result = await controller(
        flow,
        ActionRegistry(),
        change_rules={
            "date": ChangeRule(
                reset_action="change_date",
                next_state=BookingState.SELECTING_DATE,
                applied_state=BookingState.SELECTING_PEOPLE,
                prompt_template="change_ask_date",
            )
        },
    ).handle_turn(
        context,
        DialogTurnInput("change_info", {"change_target": "date"}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.SELECTING_DATE
    assert result.instruction_template == "change_ask_date"
    assert result.executed_actions == ()
    assert context.booking_date == date(2026, 10, 29)
    assert context.num_customer == 1
    assert context.duration_minutes == 60
    assert context.main_course == selected_course
    assert context.start_time == time(11, 0)


@pytest.mark.asyncio
async def test_select_date_after_change_prompt_revalidates_slots_without_asking_people() -> None:
    selected_course = main_course("09")

    async def load_time_slots(action_context: ActionExecutionContext) -> ActionResult:
        slots = (time(11, 0), time(11, 30))
        action_context.booking_context.set_available_slots(slots)
        return ActionResult("load_time_slots", slots)

    bridge = ActionRegistry()
    bridge._actions["load_time_slots"] = load_time_slots
    flow = flow_for(
        {
            BookingState.SELECTING_DATE: state(
                transitions=(
                    FlowTransition(
                        "select_date",
                        BookingState.SELECTING_PEOPLE,
                        actions=("handle_date_selection",),
                    ),
                ),
                on_enter=FlowOnEnter("ask_date"),
            ),
            BookingState.SELECTING_PEOPLE: state(on_enter=FlowOnEnter("ask_people")),
            BookingState.SELECTING_TIME: state(on_enter=FlowOnEnter("suggest_time_slots")),
            BookingState.AWAITING_CONFIRMATION: state(on_enter=FlowOnEnter("final_confirmation")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.SELECTING_DATE,
        shop=sample_shop(),
        booking_date=date(2026, 10, 29),
        num_customer=1,
        duration_minutes=60,
        main_course=selected_course,
        start_time=time(11, 0),
        therapist_preference=TherapistPreference(TherapistPreferenceType.NONE),
        therapist_verified=True,
        available_slots=(time(11, 0),),
    )

    result = await controller(flow, bridge).handle_turn(
        context,
        DialogTurnInput("select_date", {"booking_date": date(2026, 8, 27)}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.AWAITING_CONFIRMATION
    assert result.instruction_template == "final_confirmation"
    assert result.executed_actions == ("handle_date_selection", "load_time_slots", "change_time")
    assert context.booking_date == date(2026, 8, 27)
    assert context.num_customer == 1
    assert context.main_course == selected_course
    assert context.start_time == time(11, 0)
    assert context.therapist_verified is True


@pytest.mark.asyncio
async def test_change_therapist_revalidates_direct_change_before_confirmation() -> None:
    async def change_time(action_context: ActionExecutionContext) -> ActionResult:
        action_context.booking_context.set_therapist_verified(True)
        action_context.booking_context.last_failure_code = None
        return ActionResult("change_time", action_context.payload["start_time"])

    bridge = ActionRegistry()
    bridge._actions["change_time"] = change_time
    flow = flow_for(
        {
            BookingState.AWAITING_CONFIRMATION: state(
                transitions=(FlowTransition("change_info", BookingState.AWAITING_CONFIRMATION),),
                on_enter=FlowOnEnter("final_confirmation"),
            ),
            BookingState.SELECTING_THERAPIST: state(on_enter=FlowOnEnter("ask_therapist")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=sample_shop(),
        booking_date=date(2026, 8, 27),
        num_customer=1,
        duration_minutes=60,
        main_course=main_course("05"),
        start_time=time(10, 30),
        therapist_preference=TherapistPreference(TherapistPreferenceType.NONE),
        therapist_verified=True,
    )

    result = await controller(
        flow,
        bridge,
        change_rules={
            "therapist": ChangeRule(
                reset_action="change_therapist",
                next_state=BookingState.SELECTING_THERAPIST,
                applied_state=BookingState.SELECTING_THERAPIST,
                prompt_template="change_ask_therapist",
            )
        },
    ).handle_turn(
        context,
        DialogTurnInput(
            "change_info",
            {"change_target": "therapist", "therapist_gender": "none"},
        ),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.AWAITING_CONFIRMATION
    assert result.instruction_template == "final_confirmation"
    assert result.executed_actions == ("change_therapist", "change_time")
    assert context.therapist_verified is True


@pytest.mark.asyncio
async def test_multi_step_auto_transitions_finish_in_order() -> None:
    condition = FlowCondition("last_failure_code", "eq", "continue")
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(FlowTransition("go", BookingState.SELECTING_SHOP),)
            ),
            BookingState.SELECTING_SHOP: state(
                on_enter=FlowOnEnter("ask_shop"),
                auto_transitions=(FlowAutoTransition(condition, BookingState.SELECTING_DATE),),
            ),
            BookingState.SELECTING_DATE: state(
                on_enter=FlowOnEnter("ask_date"),
                auto_transitions=(FlowAutoTransition(condition, BookingState.SELECTING_PEOPLE),),
            ),
            BookingState.SELECTING_PEOPLE: state(on_enter=FlowOnEnter("ask_people")),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        last_failure_code="continue",
    )

    result = await controller(flow, ActionRegistry()).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.final_state is BookingState.SELECTING_PEOPLE
    assert result.instruction_template == "ask_people"
    assert result.auto_transition_count == 2


@pytest.mark.asyncio
async def test_auto_transition_cycle_is_detected_after_valid_commit() -> None:
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(FlowTransition("go", BookingState.SELECTING_SHOP),)
            ),
            BookingState.SELECTING_SHOP: state(
                auto_transitions=(
                    FlowAutoTransition(
                        FlowCondition("last_failure_code", "eq", "loop"),
                        BookingState.SELECTING_SHOP,
                    ),
                )
            ),
        }
    )
    context = BookingContext(conversation_id="c-1", last_failure_code="loop")

    result = await controller(flow, ActionRegistry()).handle_turn(
        context,
        DialogTurnInput("go", {}),
    )

    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert result.failure_code == "auto_transition_cycle_detected"
    assert result.auto_transition_count == 1
    assert context.state is BookingState.SELECTING_SHOP


@pytest.mark.asyncio
async def test_auto_transition_limit_stops_before_next_action() -> None:
    calls: list[str] = []
    bridge = ActionRegistry()
    bridge.register_action("first_auto", recording_action("first_auto", calls))
    bridge.register_action("second_auto", recording_action("second_auto", calls))
    condition = FlowCondition("last_failure_code", "eq", "continue")
    flow = flow_for(
        {
            BookingState.IDLE: state(
                transitions=(FlowTransition("go", BookingState.SELECTING_SHOP),)
            ),
            BookingState.SELECTING_SHOP: state(
                auto_transitions=(
                    FlowAutoTransition(
                        condition,
                        BookingState.SELECTING_DATE,
                        ("first_auto",),
                    ),
                )
            ),
            BookingState.SELECTING_DATE: state(
                auto_transitions=(
                    FlowAutoTransition(
                        condition,
                        BookingState.SELECTING_PEOPLE,
                        ("second_auto",),
                    ),
                )
            ),
            BookingState.SELECTING_PEOPLE: state(),
        }
    )
    context = BookingContext(
        conversation_id="c-1",
        last_failure_code="continue",
    )

    result = await controller(
        flow,
        bridge,
        max_auto_transitions=1,
    ).handle_turn(context, DialogTurnInput("go", {}))

    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert result.failure_code == "auto_transition_limit_exceeded"
    assert result.auto_transition_count == 1
    assert calls == ["first_auto"]
    assert context.state is BookingState.SELECTING_DATE
