"""Integration tests for deterministic NLU against the real dialog flow."""

from datetime import date, time
from pathlib import Path

import pytest

from app.dialog.flow_loader import FlowLoader
from app.dialog.nlu import (
    DeterministicNLU,
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResultNotDispatchableError,
    StateIntentPolicy,
    build_state_intent_policy,
    to_dialog_turn_input,
)
from app.dialog.state_machine import StateMachine
from app.dialog.tool_bridge import ActionExecutionContext, ToolBridge
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState

FLOW_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "dialog"
    / "flows"
    / "booking-flow.json"
)
PARSER_OUTPUT_INTENTS = {
    "ask_question",
    "cancel_flow",
    "change_info",
    "confirm",
    "deny",
    "greeting",
    "provide_phone",
    "select_date",
    "select_duration",
    "select_people",
    "select_time",
    "start_booking",
    "thanks",
    "unknown",
}
OUT_OF_FLOW_INTENTS = {"ask_question"}
SYSTEM_EVENTS = {"booking_failed", "booking_succeeded", "cancel_flow"}


def nlu(policy: StateIntentPolicy) -> DeterministicNLU:
    return DeterministicNLU(
        intent_policy=policy,
        today_provider=lambda: date(2026, 8, 1),
    )


def flow_intents() -> set[str]:
    flow = FlowLoader.load(FLOW_PATH)
    return {
        transition.intent
        for state in flow.states.values()
        for transition in state.transitions
    }


def test_parser_output_intents_are_supported_by_real_flow_or_system_policy() -> None:
    declared = flow_intents()

    assert PARSER_OUTPUT_INTENTS - SYSTEM_EVENTS - OUT_OF_FLOW_INTENTS <= declared
    assert PARSER_OUTPUT_INTENTS - declared == OUT_OF_FLOW_INTENTS
    assert declared - PARSER_OUTPUT_INTENTS - SYSTEM_EVENTS == {
        "*",
        "select_course",
        "select_store",
        "select_therapist",
    }


def test_runtime_policy_allows_faq_without_flow_transitions() -> None:
    flow = FlowLoader.load(FLOW_PATH)
    policy = build_state_intent_policy(flow, enable_faq=True)

    assert "ask_question" not in flow_intents()
    for state in {
        BookingState.IDLE,
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
        BookingState.COMPLETED,
        BookingState.CANCELLED,
    }:
        assert policy.is_allowed(state, "ask_question")


@pytest.mark.asyncio
async def test_people_result_runs_through_real_flow_and_domain_action() -> None:
    flow = FlowLoader.load(FLOW_PATH)
    policy = build_state_intent_policy(flow)
    context = BookingContext("conversation-1", state=BookingState.SELECTING_PEOPLE)
    parsed = nlu(policy).parse(text="2 người", state=context.state)
    turn = to_dialog_turn_input(
        parsed,
        state=context.state,
        intent_policy=policy,
    )
    transition = StateMachine(flow).resolve_transition(context, turn.intent)

    report = await ToolBridge().execute_actions(
        transition.actions,
        ActionExecutionContext(context, turn.intent, turn.payload),
    )

    assert report.executed_action_names == ("handle_people_selection",)
    assert context.num_customer == 2
    assert context.state is BookingState.SELECTING_PEOPLE


def test_date_and_time_entities_keep_standard_library_types() -> None:
    flow = FlowLoader.load(FLOW_PATH)
    parser = nlu(build_state_intent_policy(flow))
    parsed_date = parser.parse(text="ngày mai", state=BookingState.SELECTING_DATE)
    parsed_time = parser.parse(text="19h30", state=BookingState.SELECTING_TIME)

    assert parsed_date.payload["booking_date"] == date(2026, 8, 2)
    assert type(parsed_date.payload["booking_date"]) is date
    assert parsed_time.payload["start_time"] == time(19, 30)
    assert type(parsed_time.payload["start_time"]) is time


def test_unknown_has_wildcard_route_in_every_conversational_state() -> None:
    flow = FlowLoader.load(FLOW_PATH)
    policy = build_state_intent_policy(flow)
    conversational_states = {
        BookingState.IDLE,
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
    }

    for state in conversational_states:
        assert policy.is_allowed(state, "unknown")
        assert policy.has_wildcard(state)
        assert "*" not in policy.allowed_for(state)


@pytest.mark.parametrize(
    ("state", "text", "kind"),
    [
        (BookingState.SELECTING_SHOP, "chi nhánh quận 1", NLUEntityKind.SHOP),
        (
            BookingState.SELECTING_SERVICE,
            "massage thái",
            NLUEntityKind.COURSE,
        ),
        (
            BookingState.SELECTING_THERAPIST,
            "kỹ thuật viên nữ",
            NLUEntityKind.THERAPIST,
        ),
    ],
)
def test_query_entities_are_not_dispatched_to_domain_selection_actions(
    state: BookingState,
    text: str,
    kind: NLUEntityKind,
) -> None:
    flow = FlowLoader.load(FLOW_PATH)
    policy = build_state_intent_policy(flow)
    parsed = nlu(policy).parse(text=text, state=state)

    assert parsed.intent is None
    assert parsed.payload == {}
    assert parsed.entity_kind is kind
    assert parsed.resolution_status is NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED
    with pytest.raises(NLUResultNotDispatchableError):
        to_dialog_turn_input(
            parsed,
            state=state,
            intent_policy=policy,
        )


def test_parser_does_not_require_pos_or_llm_dependency() -> None:
    flow = FlowLoader.load(FLOW_PATH)
    parser = nlu(build_state_intent_policy(flow))

    assert parser.parse(text="ngày mai", state=BookingState.SELECTING_DATE).intent == (
        "select_date"
    )
