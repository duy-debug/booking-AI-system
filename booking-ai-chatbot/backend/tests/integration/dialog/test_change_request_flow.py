"""Integration tests for atomic changes to an in-progress booking context."""

from copy import deepcopy
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from app.application.action_registry import ActionRegistry
from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.dialog_controller import (
    DialogController,
    DialogTurnResult,
    DialogTurnStatus,
)
from app.dialog.flow_loader import FlowLoader
from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.dialog.nlu import (
    EntityResolutionCoordinator,
    EntityResolutionStatus,
    NLUProcessor,
    NLUResolutionStatus,
    StateIntentPolicy,
    build_state_intent_policy,
    entity_resolution_to_dialog_turn_input,
    to_dialog_turn_input,
)
from app.dialog.state_machine import StateMachine
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    Course,
    Customer,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState

FLOW_DIR = Path(__file__).resolve().parents[3] / "app" / "dialog"
OLD_SHOP = Shop(UUID("11111111-1111-1111-1111-111111111111"), "Old Shop")
NEW_SHOP = Shop(UUID("22222222-2222-2222-2222-222222222222"), "District 1")
COURSE = Course(
    UUID("33333333-3333-3333-3333-333333333333"),
    "Massage",
    60,
    Decimal("500000"),
)


def runtime() -> tuple[
    NLUProcessor,
    DialogController,
    InstructionBuilder,
    StateIntentPolicy,
]:
    flow = FlowLoader.load(FLOW_DIR / "booking_flow.json")
    policy = build_state_intent_policy(flow)
    controller = DialogController(
        flow=flow,
        state_machine=StateMachine(flow),
        action_registry=ActionRegistry(),
        change_rules=FlowLoader.load_change_handlers(
            FLOW_DIR / "booking_flow.json"
        ),
    )
    return (
        NLUProcessor(
            intent_policy=policy,
            today_provider=lambda: date(2026, 8, 1),
        ),
        controller,
        InstructionBuilder(),
        policy,
    )


def context(state: BookingState = BookingState.AWAITING_CONFIRMATION) -> BookingContext:
    return BookingContext(
        conversation_id="conversation-change",
        state=state,
        shop=OLD_SHOP,
        main_course=COURSE,
        customer=Customer("0901234567", "An"),
        booking_date=date(2026, 8, 5),
        start_time=time(10, 0),
        num_customer=1,
        duration_minutes=60,
        therapist_preference=TherapistPreference(TherapistPreferenceType.FEMALE),
        therapist_verified=True,
        available_slots=(time(10, 0), time(11, 0)),
        phone="0901234567",
        phone_confirmed=True,
        ng_list_checked=True,
    )


async def run_change(
    text: str,
    booking_context: BookingContext,
) -> tuple[DialogTurnResult, DialogResponse]:
    parser, controller, renderer, policy = runtime()
    parsed = parser.parse(text=text, state=booking_context.state)
    turn = to_dialog_turn_input(
        parsed,
        state=booking_context.state,
        intent_policy=policy,
    )
    result = await controller.handle_turn(booking_context, turn)
    return result, renderer.build_response(result=result, context=booking_context)


@pytest.mark.asyncio
async def test_change_date_without_value_resets_dependencies_and_asks_again() -> None:
    booking_context = context()

    result, response = await run_change("đổi ngày", booking_context)

    assert result.final_state is BookingState.SELECTING_DATE
    assert result.executed_actions == ("change_date",)
    assert booking_context.booking_date is None
    assert booking_context.start_time is None
    assert booking_context.therapist_preference is None
    assert booking_context.shop is OLD_SHOP
    assert booking_context.main_course is COURSE
    assert response.text == "Bạn muốn đổi sang ngày nào?"


@pytest.mark.asyncio
async def test_change_date_with_value_applies_in_one_controller_turn() -> None:
    booking_context = context()

    result, _ = await run_change("đổi sang ngày mai", booking_context)

    assert result.initial_state is BookingState.AWAITING_CONFIRMATION
    assert result.final_state is BookingState.SELECTING_PEOPLE
    assert result.executed_actions == ("change_date",)
    assert booking_context.booking_date == date(2026, 8, 2)


@pytest.mark.asyncio
async def test_change_people_from_time_state_clears_slot_and_therapist() -> None:
    booking_context = context(BookingState.SELECTING_TIME)

    result, _ = await run_change("đổi thành 2 người", booking_context)

    assert result.final_state is BookingState.SELECTING_DURATION
    assert booking_context.num_customer == 2
    assert booking_context.start_time is None
    assert booking_context.therapist_preference is None


@pytest.mark.asyncio
async def test_reselect_shop_clears_only_shop_dependencies() -> None:
    booking_context = context()

    result, response = await run_change("chọn lại cửa hàng", booking_context)

    assert result.final_state is BookingState.SELECTING_SHOP
    assert booking_context.shop is None
    assert booking_context.main_course is None
    assert booking_context.booking_date == date(2026, 8, 5)
    assert response.text == "Bạn muốn đổi sang cửa hàng nào?"


class ShopSearch:
    def __init__(self, shops: list[Shop]) -> None:
        self.shops = shops
        self.calls = 0

    async def execute(self, query: str | None = None) -> list[Shop]:
        self.calls += 1
        return self.shops


class ServiceSearch:
    async def execute(
        self,
        shop_id: UUID,
        query: str | None = None,
    ) -> list[Course]:
        return []


@pytest.mark.asyncio
async def test_change_shop_resolves_before_committing_new_shop() -> None:
    parser, controller, _, policy = runtime()
    booking_context = context()
    parsed = parser.parse(
        text="đổi sang chi nhánh Quận 1",
        state=booking_context.state,
    )
    search = ShopSearch([NEW_SHOP])
    resolver = EntityResolutionCoordinator(
        search_shop_handler=cast(SearchShopHandler, search),
        search_course_handler=cast(SearchCourseHandler, ServiceSearch()),
    )

    resolution = await resolver.resolve(
        nlu_result=parsed,
        state=booking_context.state,
        context=booking_context,
    )
    turn = entity_resolution_to_dialog_turn_input(
        resolution,
        state=booking_context.state,
        intent_policy=policy,
    )
    result = await controller.handle_turn(booking_context, turn)

    assert search.calls == 1
    assert result.final_state is BookingState.SELECTING_DATE
    assert booking_context.shop is NEW_SHOP
    assert booking_context.main_course is None


@pytest.mark.asyncio
async def test_ambiguous_shop_change_does_not_mutate_context() -> None:
    parser, _, _, _ = runtime()
    booking_context = context()
    before = deepcopy(booking_context)
    parsed = parser.parse(
        text="đổi sang chi nhánh Quận 1",
        state=booking_context.state,
    )
    resolver = EntityResolutionCoordinator(
        search_shop_handler=cast(SearchShopHandler, ShopSearch([NEW_SHOP, OLD_SHOP])),
        search_course_handler=cast(SearchCourseHandler, ServiceSearch()),
    )

    resolution = await resolver.resolve(
        nlu_result=parsed,
        state=booking_context.state,
        context=booking_context,
    )

    assert resolution.status is EntityResolutionStatus.AMBIGUOUS
    assert booking_context == before


@pytest.mark.asyncio
async def test_not_found_shop_change_does_not_mutate_context() -> None:
    parser, _, _, _ = runtime()
    booking_context = context()
    before = deepcopy(booking_context)
    parsed = parser.parse(
        text="đổi sang chi nhánh Quận 1",
        state=booking_context.state,
    )
    resolver = EntityResolutionCoordinator(
        search_shop_handler=cast(SearchShopHandler, ShopSearch([])),
        search_course_handler=cast(SearchCourseHandler, ServiceSearch()),
    )

    resolution = await resolver.resolve(
        nlu_result=parsed,
        state=booking_context.state,
        context=booking_context,
    )

    assert resolution.status is EntityResolutionStatus.NOT_FOUND
    assert booking_context == before


@pytest.mark.asyncio
async def test_invalid_people_change_rolls_back_old_context() -> None:
    booking_context = context()
    before = deepcopy(booking_context)

    result, response = await run_change("đổi thành 5 người", booking_context)

    assert result.status is DialogTurnStatus.FAILURE_HANDLED
    before.last_failure_code = result.failure_code
    assert booking_context == before
    assert "Dữ liệu đặt lịch cũ vẫn được giữ nguyên" in response.text


def test_completed_change_is_not_dispatchable_and_does_not_mutate() -> None:
    parser, _, _, _ = runtime()
    booking_context = context(BookingState.COMPLETED)
    before = deepcopy(booking_context)

    parsed = parser.parse(text="đổi ngày", state=booking_context.state)

    assert parsed.resolution_status is NLUResolutionStatus.UNRESOLVED
    assert booking_context == before


def test_non_change_sentence_keeps_existing_nlu_behavior() -> None:
    parser, _, _, _ = runtime()

    parsed = parser.parse(
        text="ok chốt giúp mình",
        state=BookingState.AWAITING_CONFIRMATION,
    )

    assert parsed.intent != "change_info"
