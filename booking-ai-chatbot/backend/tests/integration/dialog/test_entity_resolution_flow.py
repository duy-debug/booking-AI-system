"""Integration tests across NLU, entity resolution and dialog-turn contracts."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.flow_loader import FlowLoader
from app.dialog.nlu import (
    EntityResolutionCoordinator,
    EntityResolutionNotDispatchableError,
    EntityResolutionStatus,
    NLUProcessor,
    StateIntentPolicy,
    build_state_intent_policy,
    entity_resolution_to_dialog_turn_input,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_models import Course, CourseSelection, Shop
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome, HandlerResult

FLOW_PATH = Path(__file__).resolve().parents[3] / "app" / "dialog" / "booking_flow.json"
SHOP = Shop(UUID("11111111-1111-1111-1111-111111111111"), "Sen Spa")
OTHER_SHOP = Shop(UUID("22222222-2222-2222-2222-222222222222"), "Sen Riverside")
COURSE = Course(
    UUID("33333333-3333-3333-3333-333333333333"),
    "Massage thư giãn",
    60,
    Decimal("500000"),
)


class ShopHandler:
    def __init__(self, values: list[Shop]) -> None:
        self.values = values
        self.calls = 0

    async def execute(self, query: str | None = None) -> HandlerResult:
        self.calls += 1
        if not self.values:
            return HandlerResult(
                HandlerOutcome.NOT_FOUND,
                error_code="shop_not_found",
            )
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"shops": tuple(self.values)},
        )


class ServiceHandler:
    def __init__(self, values: list[Course]) -> None:
        self.values = values
        self.calls = 0

    async def execute(
        self,
        shop_id: UUID,
        query: str | None = None,
        **kwargs: object,
    ) -> HandlerResult:
        self.calls += 1
        if not self.values:
            return HandlerResult(
                HandlerOutcome.NOT_FOUND,
                error_code="course_not_found",
            )
        outcome = HandlerOutcome.AMBIGUOUS if len(self.values) > 1 else HandlerOutcome.SUCCESS
        return HandlerResult(outcome, {"courses": tuple(self.values)})


def components(
    shops: list[Shop],
    courses: list[Course],
) -> tuple[
    NLUProcessor,
    EntityResolutionCoordinator,
    StateIntentPolicy,
    ShopHandler,
    ServiceHandler,
]:
    flow = FlowLoader.load(FLOW_PATH)
    policy = build_state_intent_policy(flow)
    shop_handler = ShopHandler(shops)
    service_handler = ServiceHandler(courses)
    resolver = EntityResolutionCoordinator(
        search_shop_handler=cast(SearchShopHandler, shop_handler),
        search_course_handler=cast(SearchCourseHandler, service_handler),
    )
    parser = NLUProcessor(
        intent_policy=policy,
        today_provider=lambda: date(2026, 8, 1),
    )
    return parser, resolver, policy, shop_handler, service_handler


@pytest.mark.asyncio
async def test_shop_nlu_resolves_real_shop_and_maps_to_dialog_turn() -> None:
    parser, resolver, policy, shop_handler, _ = components([SHOP], [])
    context = BookingContext("conversation-1", state=BookingState.SELECTING_SHOP)
    snapshot = deepcopy(context)
    parsed = parser.parse(text="chi nhánh quận 1", state=context.state)

    resolved = await resolver.resolve(
        nlu_result=parsed,
        state=context.state,
        context=context,
    )
    turn = entity_resolution_to_dialog_turn_input(
        resolved,
        state=context.state,
        intent_policy=policy,
    )

    assert turn.intent == "select_store"
    assert turn.payload == {"shop": SHOP}
    assert type(turn.payload["shop"]) is Shop
    assert shop_handler.calls == 1
    assert context == snapshot


@pytest.mark.asyncio
async def test_course_nlu_resolves_domain_course_selection() -> None:
    parser, resolver, policy, _, service_handler = components([], [COURSE])
    context = BookingContext(
        "conversation-1",
        state=BookingState.SELECTING_SERVICE,
        shop=SHOP,
        duration_minutes=60,
    )
    snapshot = deepcopy(context)
    parsed = parser.parse(text="massage thư giãn", state=context.state)

    resolved = await resolver.resolve(
        nlu_result=parsed,
        state=context.state,
        context=context,
    )
    turn = entity_resolution_to_dialog_turn_input(
        resolved,
        state=context.state,
        intent_policy=policy,
    )

    assert turn.intent == "select_course"
    assert turn.payload == {"course_selection": CourseSelection(COURSE)}
    assert service_handler.calls == 1
    assert context == snapshot


@pytest.mark.parametrize(
    ("shops", "expected_status"),
    [
        ([SHOP, OTHER_SHOP], EntityResolutionStatus.AMBIGUOUS),
        ([], EntityResolutionStatus.NOT_FOUND),
    ],
)
@pytest.mark.asyncio
async def test_non_resolved_shop_result_never_maps_to_dialog_turn(
    shops: list[Shop],
    expected_status: EntityResolutionStatus,
) -> None:
    parser, resolver, policy, _, _ = components(shops, [])
    context = BookingContext("conversation-1", state=BookingState.SELECTING_SHOP)
    parsed = parser.parse(text="sen", state=context.state)

    result = await resolver.resolve(
        nlu_result=parsed,
        state=context.state,
        context=context,
    )

    assert result.status is expected_status
    with pytest.raises(EntityResolutionNotDispatchableError):
        entity_resolution_to_dialog_turn_input(
            result,
            state=context.state,
            intent_policy=policy,
        )


@pytest.mark.asyncio
async def test_therapist_name_fails_safely_without_availability_gateway() -> None:
    parser, resolver, _, shop_handler, service_handler = components([SHOP], [COURSE])
    context = BookingContext(
        "conversation-1",
        state=BookingState.SELECTING_THERAPIST,
        num_customer=1,
    )
    parsed = parser.parse(text="chọn chị Lan", state=context.state)

    result = await resolver.resolve(
        nlu_result=parsed,
        state=context.state,
        context=context,
    )

    assert result.status is EntityResolutionStatus.FAILED
    assert result.failure_code == "therapist_resolution_unavailable"
    assert shop_handler.calls == 0
    assert service_handler.calls == 0
