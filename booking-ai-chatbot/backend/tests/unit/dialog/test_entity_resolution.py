"""Unit tests for safe dialog-layer entity resolution."""

from copy import deepcopy
from decimal import Decimal
from types import MappingProxyType
from typing import cast
from uuid import UUID

import pytest

from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dialog.nlu import (
    EntityCandidate,
    EntityResolutionCoordinator,
    EntityResolutionNotDispatchableError,
    EntityResolutionResult,
    EntityResolutionStatus,
    InvalidCandidateSelectionError,
    InvalidEntityResolutionRequestError,
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResult,
    NLUSource,
    StateIntentPolicy,
    entity_resolution_to_dialog_turn_input,
)
from app.domain.booking_context import BookingContext, CourseSelectionMode
from app.domain.booking_models import (
    Course,
    CourseSelection,
    CourseType,
    Shop,
    TherapistPreference,
    TherapistPreferenceType,
)
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome, HandlerResult

SHOP = Shop(
    UUID("11111111-1111-1111-1111-111111111111"),
    "Sen Spa",
    "Quận 1",
)
OTHER_SHOP = Shop(
    UUID("22222222-2222-2222-2222-222222222222"),
    "Sen Riverside",
    "Quận 2",
)
MAIN = Course(
    UUID("33333333-3333-3333-3333-333333333333"),
    "Massage thư giãn",
    60,
    Decimal("500000"),
)
OTHER_MAIN = Course(
    UUID("44444444-4444-4444-4444-444444444444"),
    "Massage Thái",
    90,
    Decimal("700000"),
)
ADDON = Course(
    UUID("55555555-5555-5555-5555-555555555555"),
    "Đá nóng",
    15,
    Decimal("100000"),
    CourseType.ADDON,
)


class FakeSearchShopHandler:
    def __init__(
        self,
        results: list[Shop] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls = 0
        self.received_query: str | None = None

    async def execute(self, query: str | None = None) -> HandlerResult:
        self.calls += 1
        self.received_query = query
        if self.error is not None:
            raise self.error
        if not self.results:
            return HandlerResult(
                HandlerOutcome.NOT_FOUND,
                error_code="shop_not_found",
            )
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"shops": tuple(self.results)},
        )


class FakeSearchCourseHandler:
    def __init__(
        self,
        results: list[Course] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls = 0
        self.received_shop_id: UUID | None = None
        self.received_query: str | None = None
        self.received_course_type: CourseType | None = None

    async def execute(
        self,
        shop_id: UUID,
        query: str | None = None,
        **kwargs: object,
    ) -> HandlerResult:
        self.calls += 1
        self.received_shop_id = shop_id
        self.received_query = query
        course_type = kwargs.get("course_type")
        self.received_course_type = course_type if isinstance(course_type, CourseType) else None
        if self.error is not None:
            raise self.error
        if not self.results:
            return HandlerResult(
                HandlerOutcome.NOT_FOUND,
                error_code="course_not_found",
            )
        outcome = HandlerOutcome.AMBIGUOUS if len(self.results) > 1 else HandlerOutcome.SUCCESS
        return HandlerResult(outcome, {"courses": tuple(self.results)})


def coordinator(
    shops: FakeSearchShopHandler | None = None,
    courses: FakeSearchCourseHandler | None = None,
) -> EntityResolutionCoordinator:
    return EntityResolutionCoordinator(
        search_shop_handler=cast(SearchShopHandler, shops or FakeSearchShopHandler()),
        search_course_handler=cast(
            SearchCourseHandler,
            courses or FakeSearchCourseHandler(),
        ),
    )


def entity_request(kind: NLUEntityKind, query: str) -> NLUResult:
    return NLUResult(
        intent=None,
        payload={},
        confidence=0.8,
        source=NLUSource.DETERMINISTIC,
        resolution_status=NLUResolutionStatus.ENTITY_RESOLUTION_REQUIRED,
        matched_rule=f"{kind.value}_query_state",
        entity_query=query,
        entity_kind=kind,
    )


def policy() -> StateIntentPolicy:
    return StateIntentPolicy(
        {
            BookingState.SELECTING_SHOP: frozenset({"select_store"}),
            BookingState.SELECTING_SERVICE: frozenset({"select_course"}),
            BookingState.SELECTING_THERAPIST: frozenset({"select_therapist"}),
        },
        frozenset(),
    )


def test_candidate_is_immutable_and_filters_unsafe_metadata() -> None:
    candidate = EntityCandidate(
        NLUEntityKind.COURSE,
        "Massage",
        "course:0",
        {
            "duration_minutes": 60,
            "price": Decimal("500000"),
            "course_id": str(MAIN.course_id),
            "token": "secret",
        },
    )

    assert candidate.metadata == {
        "duration_minutes": 60,
        "price": Decimal("500000"),
    }
    assert str(MAIN.course_id) not in repr(candidate.metadata)
    assert isinstance(candidate.metadata, MappingProxyType)


@pytest.mark.asyncio
async def test_invalid_nlu_result_and_wrong_state_are_rejected() -> None:
    resolved = NLUResult(
        "unknown",
        {},
        0.0,
        NLUSource.FALLBACK,
        NLUResolutionStatus.RESOLVED,
    )
    resolver = coordinator()

    with pytest.raises(InvalidEntityResolutionRequestError):
        await resolver.resolve(
            nlu_result=resolved,
            state=BookingState.SELECTING_SHOP,
            context=BookingContext("conversation-1"),
        )
    with pytest.raises(InvalidEntityResolutionRequestError):
        await resolver.resolve(
            nlu_result=entity_request(NLUEntityKind.SHOP, "quận 1"),
            state=BookingState.SELECTING_TIME,
            context=BookingContext("conversation-1"),
        )


@pytest.mark.asyncio
async def test_shop_not_found_calls_handler_once() -> None:
    handler = FakeSearchShopHandler()

    result = await coordinator(shops=handler).resolve(
        nlu_result=entity_request(NLUEntityKind.SHOP, "quận 9"),
        state=BookingState.SELECTING_SHOP,
        context=BookingContext("conversation-1"),
    )

    assert result.status is EntityResolutionStatus.NOT_FOUND
    assert result.failure_code == "shop_not_found"
    assert handler.calls == 1
    assert handler.received_query == "quận 9"


@pytest.mark.asyncio
async def test_one_shop_resolves_exact_action_registry_payload_without_mutation() -> None:
    handler = FakeSearchShopHandler([SHOP])
    context = BookingContext("conversation-1", state=BookingState.SELECTING_SHOP)
    snapshot = deepcopy(context)

    result = await coordinator(shops=handler).resolve(
        nlu_result=entity_request(NLUEntityKind.SHOP, "sen"),
        state=context.state,
        context=context,
    )

    assert result.status is EntityResolutionStatus.RESOLVED
    assert result.dispatch_intent == "select_store"
    assert result.dispatch_payload == {"shop": SHOP}
    assert handler.calls == 1
    assert context == snapshot


@pytest.mark.asyncio
async def test_multiple_shops_are_ambiguous_and_preserve_order_without_uuid() -> None:
    result = await coordinator(shops=FakeSearchShopHandler([SHOP, OTHER_SHOP])).resolve(
        nlu_result=entity_request(NLUEntityKind.SHOP, "sen"),
        state=BookingState.SELECTING_SHOP,
        context=BookingContext("conversation-1"),
    )

    assert result.status is EntityResolutionStatus.AMBIGUOUS
    assert result.dispatch_intent is None
    assert tuple(item.display_name for item in result.candidates) == (
        SHOP.name,
        OTHER_SHOP.name,
    )
    assert tuple(item.selection_key for item in result.candidates) == (
        "shop:0",
        "shop:1",
    )
    assert str(SHOP.shop_id) not in repr(result.candidates)


@pytest.mark.asyncio
async def test_shop_handler_exception_becomes_safe_failed_result() -> None:
    secret = "raw-gateway-secret"
    result = await coordinator(shops=FakeSearchShopHandler(error=RuntimeError(secret))).resolve(
        nlu_result=entity_request(NLUEntityKind.SHOP, "sen"),
        state=BookingState.SELECTING_SHOP,
        context=BookingContext("conversation-1"),
    )

    assert result.status is EntityResolutionStatus.FAILED
    assert result.failure_code == "shop_resolution_unavailable"
    assert secret not in repr(result)


@pytest.mark.asyncio
async def test_course_requires_shop_before_handler_call() -> None:
    handler = FakeSearchCourseHandler([MAIN])

    result = await coordinator(courses=handler).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "massage"),
        state=BookingState.SELECTING_SERVICE,
        context=BookingContext("conversation-1"),
    )

    assert result.status is EntityResolutionStatus.FAILED
    assert result.failure_code == "shop_required_before_course_resolution"
    assert handler.calls == 0


@pytest.mark.asyncio
async def test_course_not_found_uses_shop_and_query_once() -> None:
    handler = FakeSearchCourseHandler()
    context = BookingContext("conversation-1", shop=SHOP)

    result = await coordinator(courses=handler).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "không có"),
        state=BookingState.SELECTING_SERVICE,
        context=context,
    )

    assert result.status is EntityResolutionStatus.NOT_FOUND
    assert result.failure_code == "course_not_found"
    assert handler.calls == 1
    assert handler.received_shop_id == SHOP.shop_id
    assert handler.received_query == "không có"


@pytest.mark.asyncio
async def test_one_main_course_resolves_course_selection_without_context_mutation() -> None:
    handler = FakeSearchCourseHandler([MAIN])
    context = BookingContext(
        "conversation-1",
        state=BookingState.SELECTING_SERVICE,
        shop=SHOP,
        duration_minutes=60,
    )
    snapshot = deepcopy(context)

    result = await coordinator(courses=handler).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "massage"),
        state=context.state,
        context=context,
    )

    assert result.status is EntityResolutionStatus.RESOLVED
    assert result.dispatch_payload == {"course_selection": CourseSelection(MAIN)}
    assert context == snapshot
    assert context.duration_minutes == 60
    assert handler.received_course_type is CourseType.MAIN


@pytest.mark.asyncio
async def test_course_resolution_uses_selected_duration_to_disambiguate_main_course() -> None:
    context = BookingContext(
        "conversation-1",
        state=BookingState.SELECTING_SERVICE,
        shop=SHOP,
        duration_minutes=60,
    )

    result = await coordinator(courses=FakeSearchCourseHandler([MAIN, OTHER_MAIN])).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "massage"),
        state=context.state,
        context=context,
    )

    assert result.status is EntityResolutionStatus.RESOLVED
    assert result.dispatch_payload == {"course_selection": CourseSelection(MAIN)}


@pytest.mark.asyncio
async def test_addon_preserves_type_and_requires_existing_main_course() -> None:
    without_main = await coordinator(courses=FakeSearchCourseHandler([ADDON])).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "đá nóng"),
        state=BookingState.SELECTING_SERVICE,
        context=BookingContext("conversation-1", shop=SHOP),
    )
    with_main = await coordinator(courses=FakeSearchCourseHandler([ADDON])).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "đá nóng"),
        state=BookingState.SELECTING_SERVICE,
        context=BookingContext(
            "conversation-1",
            shop=SHOP,
            main_course=MAIN,
            course_selection_mode=CourseSelectionMode.ADDON,
        ),
    )

    assert without_main.status is EntityResolutionStatus.UNSUPPORTED
    assert without_main.failure_code == "main_course_required"
    assert with_main.dispatch_payload == {"course_selection": CourseSelection(MAIN, (ADDON,))}
    assert ADDON.course_type is CourseType.ADDON


@pytest.mark.asyncio
async def test_addon_mode_queries_only_addons() -> None:
    handler = FakeSearchCourseHandler([ADDON])
    context = BookingContext(
        "conversation-addon-mode",
        state=BookingState.SELECTING_SERVICE,
        shop=SHOP,
        main_course=MAIN,
        course_selection_mode=CourseSelectionMode.ADDON,
    )

    await coordinator(courses=handler).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "đá nóng"),
        state=context.state,
        context=context,
    )

    assert handler.received_course_type is CourseType.ADDON


@pytest.mark.asyncio
async def test_multiple_courses_are_ambiguous_with_decimal_metadata() -> None:
    result = await coordinator(courses=FakeSearchCourseHandler([MAIN, OTHER_MAIN])).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "massage"),
        state=BookingState.SELECTING_SERVICE,
        context=BookingContext("conversation-1", shop=SHOP),
    )

    assert result.status is EntityResolutionStatus.AMBIGUOUS
    assert tuple(item.display_name for item in result.candidates) == (
        MAIN.name,
        OTHER_MAIN.name,
    )
    assert result.candidates[0].metadata["price"] == Decimal("500000")
    assert isinstance(result.candidates[0].metadata["price"], Decimal)
    assert str(MAIN.course_id) not in repr(result.candidates)


@pytest.mark.asyncio
async def test_course_handler_exception_becomes_safe_failure() -> None:
    secret = "malformed-response-secret"
    result = await coordinator(courses=FakeSearchCourseHandler(error=RuntimeError(secret))).resolve(
        nlu_result=entity_request(NLUEntityKind.COURSE, "massage"),
        state=BookingState.SELECTING_SERVICE,
        context=BookingContext("conversation-1", shop=SHOP),
    )

    assert result.status is EntityResolutionStatus.FAILED
    assert result.failure_code == "course_resolution_unavailable"
    assert secret not in repr(result)


@pytest.mark.asyncio
async def test_therapist_name_needs_gateway_and_gender_maps_without_handlers() -> None:
    name_result = await coordinator().resolve(
        nlu_result=entity_request(NLUEntityKind.THERAPIST, "lan"),
        state=BookingState.SELECTING_THERAPIST,
        context=BookingContext("conversation-1", num_customer=1),
    )
    gender_result = await coordinator().resolve(
        nlu_result=entity_request(NLUEntityKind.THERAPIST, "female"),
        state=BookingState.SELECTING_THERAPIST,
        context=BookingContext("conversation-1"),
    )

    assert name_result.status is EntityResolutionStatus.FAILED
    assert name_result.failure_code == "therapist_resolution_unavailable"
    assert gender_result.status is EntityResolutionStatus.RESOLVED
    preference = gender_result.dispatch_payload["therapist_preference"]
    assert preference == TherapistPreference(TherapistPreferenceType.FEMALE)
    assert not hasattr(preference, "therapist_uuid")


@pytest.mark.asyncio
async def test_candidate_selection_is_pure_and_does_not_repeat_handler_call() -> None:
    handler = FakeSearchShopHandler([SHOP, OTHER_SHOP])
    resolver = coordinator(shops=handler)
    ambiguous = await resolver.resolve(
        nlu_result=entity_request(NLUEntityKind.SHOP, "sen"),
        state=BookingState.SELECTING_SHOP,
        context=BookingContext("conversation-1"),
    )

    selected = resolver.select_candidate(result=ambiguous, selection_key="shop:1")

    assert selected.status is EntityResolutionStatus.RESOLVED
    assert selected.dispatch_payload == {"shop": OTHER_SHOP}
    assert handler.calls == 1
    assert ambiguous.status is EntityResolutionStatus.AMBIGUOUS
    with pytest.raises(InvalidCandidateSelectionError):
        resolver.select_candidate(result=ambiguous, selection_key="shop:99")
    with pytest.raises(InvalidCandidateSelectionError):
        resolver.select_candidate(result=selected, selection_key="shop:1")


def resolved_shop_result() -> EntityResolutionResult:
    return EntityResolutionResult(
        EntityResolutionStatus.RESOLVED,
        NLUEntityKind.SHOP,
        "select_store",
        {"shop": SHOP},
        matched_count=1,
    )


def test_resolution_mapper_preserves_domain_type_and_idempotency_key() -> None:
    turn = entity_resolution_to_dialog_turn_input(
        resolved_shop_result(),
        state=BookingState.SELECTING_SHOP,
        intent_policy=policy(),
        idempotency_key="stable-key",
    )

    assert turn.intent == "select_store"
    assert turn.payload == {"shop": SHOP}
    assert type(turn.payload["shop"]) is Shop
    assert turn.idempotency_key == "stable-key"


@pytest.mark.parametrize(
    "result",
    [
        EntityResolutionResult(
            EntityResolutionStatus.NOT_FOUND,
            NLUEntityKind.SHOP,
            None,
            {},
            failure_code="shop_not_found",
        ),
        EntityResolutionResult(
            EntityResolutionStatus.UNSUPPORTED,
            NLUEntityKind.THERAPIST,
            None,
            {},
            failure_code="therapist_lookup_not_supported",
        ),
        EntityResolutionResult(
            EntityResolutionStatus.FAILED,
            NLUEntityKind.COURSE,
            None,
            {},
            failure_code="course_resolution_unavailable",
        ),
    ],
)
def test_resolution_mapper_rejects_non_resolved_statuses(
    result: EntityResolutionResult,
) -> None:
    with pytest.raises(EntityResolutionNotDispatchableError):
        entity_resolution_to_dialog_turn_input(
            result,
            state=BookingState.SELECTING_SHOP,
            intent_policy=policy(),
        )


def test_resolution_mapper_rejects_disallowed_intent_and_wrong_payload_type() -> None:
    wrong_payload = EntityResolutionResult(
        EntityResolutionStatus.RESOLVED,
        NLUEntityKind.SHOP,
        "select_store",
        {"shop": "not-a-shop"},
        matched_count=1,
    )

    with pytest.raises(EntityResolutionNotDispatchableError):
        entity_resolution_to_dialog_turn_input(
            resolved_shop_result(),
            state=BookingState.SELECTING_SERVICE,
            intent_policy=policy(),
        )
    with pytest.raises(EntityResolutionNotDispatchableError):
        entity_resolution_to_dialog_turn_input(
            wrong_payload,
            state=BookingState.SELECTING_SHOP,
            intent_policy=policy(),
        )
