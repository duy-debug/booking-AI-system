"""Integration tests for the non-streaming FastAPI chat endpoint."""

import json
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.dependencies as dependencies
from app.application.handlers.check_availability_handler import CheckAvailabilityHandler
from app.application.handlers.search_course_handler import SearchCourseHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dependencies import ApplicationContainer
from app.dialog.nlu import (
    EntityCandidate,
    EntityResolutionCoordinator,
    EntityResolutionResult,
    EntityResolutionStatus,
    LLMNLUFallback,
    NLUEntityKind,
    NLUProcessor,
    NLUResolutionStatus,
    NLUResult,
    NLUSource,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_models import Course, CourseSelection, CourseType, Shop
from app.domain.booking_state import BookingState
from app.infrastructure.context_store import Settings
from app.infrastructure.gemini_client import LLMMessage, LLMResponse
from app.infrastructure.qdrant_client import FAQManager, KnowledgeDocument
from app.main import create_app

SHOP = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Shibuya",
    address="Tokyo",
)
COURSE = Course(
    course_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)
ADDON = Course(
    course_id=UUID("55555555-5555-5555-5555-555555555555"),
    name="Chăm sóc da đầu",
    duration_minutes=15,
    price=Decimal("100000.00"),
    course_type=CourseType.ADDON,
)


class RecordingSearchShopHandler(SearchShopHandler):
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def execute(self, query: str | None = None) -> list[Shop]:
        self.calls.append(query)
        return [SHOP]


class RecordingDiscoveryShopHandler(SearchShopHandler):
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def execute(self, query: str | None = None) -> list[Shop]:
        self.calls.append(query)
        return [
            SHOP,
            Shop(
                shop_id=UUID("33333333-3333-3333-3333-333333333333"),
                name="Komorebi Huế",
                address="Huế",
            ),
        ]


class RecordingDiscoveryCourseHandler(SearchCourseHandler):
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, CourseType | None]] = []

    async def execute(
        self,
        shop_id: UUID,
        query: str | None = None,
        *,
        course_type: CourseType | None = None,
        is_active: bool = True,
    ) -> list[Course]:
        self.calls.append((shop_id, course_type))
        return [ADDON] if course_type is CourseType.ADDON else [COURSE]


class RecordingAvailabilityHandler(CheckAvailabilityHandler):
    def __init__(self) -> None:
        self.calls: list[BookingContext] = []
        self.slots = (time(10, 30), time(11, 0))

    async def execute(self, context: BookingContext) -> tuple[time, ...]:
        self.calls.append(context)
        context.set_available_slots(self.slots)
        return self.slots


class StaticResolver:
    def __init__(self, result: EntityResolutionResult) -> None:
        self.result = result
        self.calls = 0

    async def resolve(
        self,
        *,
        nlu_result: NLUResult,
        state: BookingState,
        context: BookingContext,
    ) -> EntityResolutionResult:
        self.calls += 1
        return self.result


class StaticLLMGateway:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content=self.content)


class StaticKnowledgeGateway:
    def __init__(self, documents: list[KnowledgeDocument]) -> None:
        self.documents = documents
        self.calls: list[tuple[str, int]] = []

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeDocument]:
        self.calls.append((query, limit))
        return self.documents


class AlwaysUnresolvedNLU:
    def parse(self, *, text: str, state: BookingState) -> NLUResult:
        return NLUResult(
            intent=None,
            payload={},
            confidence=0.0,
            source=NLUSource.FALLBACK,
            resolution_status=NLUResolutionStatus.UNRESOLVED,
        )


@pytest.fixture
def chat_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, list[httpx.Request]]]:
    outbound_requests: list[httpx.Request] = []

    def reject_external_request(request: httpx.Request) -> httpx.Response:
        outbound_requests.append(request)
        return httpx.Response(500, request=request)

    outbound_client = httpx.AsyncClient(
        transport=httpx.MockTransport(reject_external_request),
        base_url="http://pos.test",
    )
    monkeypatch.setattr(
        dependencies.httpx,
        "AsyncClient",
        lambda **kwargs: outbound_client,
    )
    application = create_app(Settings(pos_base_url="http://pos.test"))
    with TestClient(application) as client:
        container = cast(
            ApplicationContainer,
            application.state.application_container,
        )

        container.action_registry._search_shop_handler = RecordingSearchShopHandler()
        yield client, outbound_requests


def container_of(client: TestClient) -> ApplicationContainer:
    application = cast(FastAPI, client.app)
    return cast(ApplicationContainer, application.state.application_container)


def post_message(
    client: TestClient,
    *,
    conversation_id: str,
    message: str,
    idempotency_key: str | None = None,
) -> httpx.Response:
    payload: dict[str, str] = {
        "conversation_id": conversation_id,
        "message": message,
    }
    if idempotency_key is not None:
        payload["idempotency_key"] = idempotency_key
    return cast(httpx.Response, client.post("/api/v1/chat", json=payload))


def test_shop_discovery_enters_shop_selection_without_selecting_a_candidate(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    handler = RecordingDiscoveryShopHandler()
    container._handlers = tuple(
        handler if isinstance(item, SearchShopHandler) else item
        for item in container._handlers
    )

    response = post_message(
        client,
        conversation_id="conversation-list-shops",
        message="bạn có thể liệt kê cửa hàng cho tôi xem được không",
    )
    body = response.json()
    context = container.memory_cache._contexts["conversation-list-shops"]

    assert response.status_code == 200
    assert body["state"] == "selecting_shop"
    assert body["status"] == "success"
    assert body["quick_replies"] == ["Shibuya", "Komorebi Huế"]
    assert body["metadata"] == {"item_count": 2}
    assert "Komorebi Huế" in body["text"]
    assert handler.calls == [None]
    assert context.shop is None
    assert outbound_requests == []


def test_generic_edit_at_final_confirmation_returns_guided_change_menu(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    context = BookingContext(
        "conversation-edit-menu",
        state=BookingState.AWAITING_CONFIRMATION,
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="tôi muốn chỉnh sửa booking",
    )
    body = response.json()

    assert response.status_code == 200
    assert body["state"] == "awaiting_confirmation"
    assert body["status"] == "success"
    assert body["quick_replies"] == [
        "Đổi cửa hàng",
        "Đổi ngày",
        "Đổi số người",
        "Đổi thời lượng",
        "Đổi liệu trình",
        "Đổi giờ",
        "Đổi kỹ thuật viên",
        "Đổi số điện thoại",
    ]
    assert context.state is BookingState.AWAITING_CONFIRMATION
    assert outbound_requests == []


def test_service_package_synonym_lists_services_during_duration_selection(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    handler = RecordingDiscoveryCourseHandler()
    container._handlers = tuple(
        handler if isinstance(item, SearchCourseHandler) else item
        for item in container._handlers
    )
    context = BookingContext(
        "conversation-package-list",
        state=BookingState.SELECTING_DURATION,
        shop=SHOP,
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="cho tôi xem các gói",
    )

    assert response.status_code == 200
    assert response.json()["state"] == "selecting_duration"
    assert response.json()["quick_replies"] == [COURSE.name]
    assert handler.calls == [(SHOP.shop_id, CourseType.MAIN)]
    assert context.duration_minutes is None
    assert outbound_requests == []


def test_service_discovery_keeps_booking_selection_and_calls_pos_once(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    handler = RecordingDiscoveryCourseHandler()
    container._handlers = tuple(
        handler if isinstance(item, SearchCourseHandler) else item
        for item in container._handlers
    )
    context = BookingContext(
        "conversation-list-courses",
        state=BookingState.SELECTING_SERVICE,
        shop=SHOP,
        booking_date=date(2099, 8, 15),
        num_customer=1,
        duration_minutes=60,
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="có những liệu trình chính và add-on nào",
    )
    body = response.json()

    assert response.status_code == 200
    assert body["state"] == "selecting_service"
    assert body["status"] == "success"
    assert body["quick_replies"] == [COURSE.name]
    assert handler.calls == [(SHOP.shop_id, CourseType.MAIN)]
    assert context.main_course is None
    assert outbound_requests == []


def test_valid_idle_booking_turn_returns_json_and_persists_state(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    application = cast(FastAPI, client.app)

    response = post_message(
        client,
        conversation_id="conversation-a",
        message="Tôi muốn đặt lịch",
        idempotency_key="key-a",
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "text/event-stream" not in response.headers["content-type"]
    assert response.json()["conversation_id"] == "conversation-a"
    assert response.json()["state"] == "selecting_shop"
    search = cast(
        RecordingSearchShopHandler,
        container_of(client).action_registry._search_shop_handler,
    )
    assert search.calls == [None]
    assert set(application.openapi()["paths"]) == {
        "/api/v1/chat",
        "/api/v1/chat/stream",
    }
    assert outbound_requests == []


def test_json_happy_path_reaches_people_without_preload_calls(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)

    started = post_message(
        client,
        conversation_id="conversation-p1",
        message="Tôi muốn đặt lịch",
    )
    resolver = StaticResolver(
        EntityResolutionResult(
            status=EntityResolutionStatus.RESOLVED,
            entity_kind=NLUEntityKind.SHOP,
            dispatch_intent="select_store",
            dispatch_payload={"shop": SHOP},
            matched_count=1,
        )
    )
    container.entity_resolution_coordinator = cast(
        EntityResolutionCoordinator,
        resolver,
    )
    selected_shop = post_message(
        client,
        conversation_id="conversation-p1",
        message="Shibuya",
    )
    selected_date = post_message(
        client,
        conversation_id="conversation-p1",
        message="15/08/2099",
    )
    context = container.memory_cache._contexts["conversation-p1"]
    search = cast(
        RecordingSearchShopHandler,
        container.action_registry._search_shop_handler,
    )

    assert [
        started.json()["state"],
        selected_shop.json()["state"],
        selected_date.json()["state"],
    ] == ["selecting_shop", "selecting_date", "selecting_people"]
    assert all(
        response.json()["status"] == "success"
        for response in (started, selected_shop, selected_date)
    )
    assert context.shop is SHOP
    assert context.booking_date == date(2099, 8, 15)
    assert search.calls == [None]
    assert resolver.calls == 1
    assert outbound_requests == []


def test_booking_request_prefills_date_and_skips_redundant_date_question(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)

    started = post_message(
        client,
        conversation_id="conversation-prefilled",
        message="Tôi muốn đặt booking ngày mai vào lúc 7:00 nhé",
    )
    container.entity_resolution_coordinator = cast(
        EntityResolutionCoordinator,
        StaticResolver(
            EntityResolutionResult(
                status=EntityResolutionStatus.RESOLVED,
                entity_kind=NLUEntityKind.SHOP,
                dispatch_intent="select_store",
                dispatch_payload={"shop": SHOP},
                matched_count=1,
            )
        ),
    )
    selected_shop = post_message(
        client,
        conversation_id="conversation-prefilled",
        message="Shibuya",
    )
    context = container.memory_cache._contexts["conversation-prefilled"]

    assert started.json()["state"] == "selecting_shop"
    assert selected_shop.json()["state"] == "selecting_people"
    assert selected_shop.json()["quick_replies"] == ["1 người", "2 người", "3 người"]
    assert context.booking_date == date.today() + timedelta(days=1)
    assert context.requested_booking_date is None
    assert context.requested_start_time == time(7, 0)
    assert context.start_time is None
    assert outbound_requests == []


def test_json_phone_denial_clears_phone_and_returns_to_collection(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    context = BookingContext(
        "conversation-phone-denial",
        state=BookingState.VERIFYING_PHONE,
        shop=SHOP,
        main_course=COURSE,
        booking_date=date(2099, 8, 15),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        phone="0901234567",
        phone_confirmed=True,
        ng_list_checked=True,
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="không",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["state"] == "collecting_phone"
    assert context.phone is None
    assert context.phone_confirmed is False
    assert context.shop is SHOP
    assert context.main_course is COURSE
    assert context.booking_date == date(2099, 8, 15)
    assert context.start_time == time(10, 30)
    assert outbound_requests == []


def test_booking_proactively_suggests_main_course_then_addon_then_slots(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    service_handler = RecordingDiscoveryCourseHandler()
    container._handlers = tuple(
        service_handler if isinstance(item, SearchCourseHandler) else item
        for item in container._handlers
    )
    availability = RecordingAvailabilityHandler()
    container.action_registry._check_availability_handler = availability
    context = BookingContext(
        "conversation-guided-courses",
        state=BookingState.SELECTING_DURATION,
        shop=SHOP,
        booking_date=date(2099, 8, 15),
        num_customer=1,
    )
    container.memory_cache._contexts[context.conversation_id] = context

    main_response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="60 phút",
    )
    assert main_response.json()["state"] == "selecting_service"
    assert main_response.json()["quick_replies"] == [COURSE.name]
    assert "liệu trình chính" in main_response.json()["text"].casefold()
    assert service_handler.calls == [(SHOP.shop_id, CourseType.MAIN)]

    container.entity_resolution_coordinator = cast(
        EntityResolutionCoordinator,
        StaticResolver(
            EntityResolutionResult(
                status=EntityResolutionStatus.RESOLVED,
                entity_kind=NLUEntityKind.COURSE,
                dispatch_intent="select_course",
                dispatch_payload={
                    "course_selection": CourseSelection(main_course=COURSE)
                },
                matched_count=1,
            )
        ),
    )
    addon_response = post_message(
        client,
        conversation_id=context.conversation_id,
        message=COURSE.name,
    )
    assert addon_response.json()["state"] == "selecting_service"
    assert addon_response.json()["quick_replies"] == [
        ADDON.name,
        "Không chọn add-on",
    ]
    assert "add-on" in addon_response.json()["text"].casefold()
    assert service_handler.calls[-1] == (SHOP.shop_id, CourseType.ADDON)

    slot_response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="Không chọn add-on",
    )
    assert slot_response.json()["state"] == "selecting_time"
    assert slot_response.json()["quick_replies"] == ["10:30", "11:00"]
    assert availability.calls == [context]
    assert outbound_requests == []


def test_json_booking_failure_refreshes_slots_without_booking_creation(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    availability = RecordingAvailabilityHandler()
    container.action_registry._check_availability_handler = availability
    gateway = StaticLLMGateway(
        json.dumps(
            {
                "intent": "select_time",
                "confidence": 0.9,
                "entities": {"start_time": "10:30"},
                "entity_kind": None,
                "entity_query": None,
            }
        )
    )
    container.llm_nlu_fallback = LLMNLUFallback(
        llm_gateway=gateway,
        intent_policy=container.state_intent_policy,
    )
    context = BookingContext(
        "conversation-reload-slots",
        state=BookingState.BOOKING_FAILED,
        shop=SHOP,
        main_course=COURSE,
        booking_date=date(2099, 8, 15),
        start_time=time(9, 0),
        num_customer=1,
        duration_minutes=60,
        available_slots=(time(9, 0),),
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="10:30",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["state"] == "selecting_time"
    assert availability.calls == [context]
    assert context.available_slots == availability.slots
    assert context.start_time == time(9, 0)
    assert context.booking is None
    assert gateway.calls == 0
    assert outbound_requests == []


def test_valid_structured_llm_fallback_returns_http_200(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    gateway = StaticLLMGateway(
        json.dumps(
            {
                "intent": "start_booking",
                "confidence": 0.9,
                "entities": {},
                "entity_kind": None,
                "entity_query": None,
            }
        )
    )
    container.nlu_processor = cast(NLUProcessor, AlwaysUnresolvedNLU())
    container.llm_nlu_fallback = LLMNLUFallback(
        llm_gateway=gateway,
        intent_policy=container.state_intent_policy,
    )

    response = post_message(
        client,
        conversation_id="conversation-llm",
        message="Giúp mình bắt đầu quy trình nhé",
    )

    assert response.status_code == 200
    assert response.json()["state"] == "selecting_shop"
    assert gateway.calls == 1
    assert outbound_requests == []


def test_faq_returns_safe_json_without_state_change_or_internal_metadata(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    gateway = StaticKnowledgeGateway(
        [KnowledgeDocument("Cửa hàng mở cửa từ 09:00 đến 22:00.", 0.98, "private")]
    )
    container.faq_manager = FAQManager(
        knowledge_gateway=gateway,
        instruction_builder=container.instruction_builder,
    )

    response = post_message(
        client,
        conversation_id="conversation-faq-json",
        message="Cửa hàng mở cửa lúc mấy giờ?",
    )

    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": "conversation-faq-json",
        "text": "Cửa hàng mở cửa từ 09:00 đến 22:00.",
        "state": "idle",
        "status": "success",
        "instruction_template": None,
        "quick_replies": [],
        "metadata": {"response_type": "faq", "source_count": 1},
    }
    assert gateway.calls == [("Cửa hàng mở cửa lúc mấy giờ?", 3)]
    assert "private" not in response.text
    assert "0.98" not in response.text
    assert outbound_requests == []


def test_in_progress_change_returns_200_and_persists_atomic_result(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    context = BookingContext(
        "conversation-change",
        state=BookingState.AWAITING_CONFIRMATION,
        shop=SHOP,
        booking_date=date(2026, 8, 5),
        start_time=time(10, 0),
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="đổi ngày",
    )

    assert response.status_code == 200
    assert response.json()["state"] == "selecting_date"
    assert response.json()["text"] == "Bạn muốn đổi sang ngày nào?"
    saved = container.memory_cache._contexts[context.conversation_id]
    assert saved.booking_date is None
    assert saved.start_time is None
    assert saved.shop is SHOP
    assert outbound_requests == []


def test_completed_booking_change_is_rejected_without_mutation_or_pos_call(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    context = BookingContext(
        "conversation-completed-change",
        state=BookingState.COMPLETED,
        booking_date=date(2026, 8, 5),
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id=context.conversation_id,
        message="đổi ngày",
    )

    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    assert "Đặt lịch này đã hoàn tất" in response.json()["text"]
    assert context.booking_date == date(2026, 8, 5)
    assert outbound_requests == []


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "hello"},
        {"conversation_id": "conversation-a", "message": " "},
        {"conversation_id": "0901234567", "message": "hello"},
    ],
)
def test_invalid_request_returns_validation_error(
    chat_client: tuple[TestClient, list[httpx.Request]],
    payload: dict[str, str],
) -> None:
    client, _ = chat_client

    response = client.post("/api/v1/chat", json=payload)

    assert response.status_code == 422


def test_conversations_are_independent_and_same_conversation_is_retained(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, _ = chat_client

    first = post_message(
        client,
        conversation_id="conversation-a",
        message="Tôi muốn đặt lịch",
    )
    second = post_message(
        client,
        conversation_id="conversation-b",
        message="Tôi muốn đặt lịch",
    )
    retained = post_message(
        client,
        conversation_id="conversation-a",
        message="không có kết quả chắc chắn",
    )
    container = container_of(client)
    first_context = container.memory_cache._contexts["conversation-a"]
    second_context = container.memory_cache._contexts["conversation-b"]

    assert first.status_code == second.status_code == retained.status_code == 200
    assert first_context is not second_context
    assert first_context.state is BookingState.SELECTING_SHOP
    assert second_context.state is BookingState.SELECTING_SHOP
    assert retained.json()["state"] == "selecting_shop"


def test_prepared_people_state_processes_deterministic_turn(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    context = BookingContext(
        conversation_id="conversation-a",
        state=BookingState.SELECTING_PEOPLE,
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id="conversation-a",
        message="2 người",
    )

    assert response.status_code == 200
    assert response.json()["state"] == "selecting_duration"
    assert context.num_customer == 2
    assert outbound_requests == []


def test_single_entity_result_runs_through_resolver_and_controller(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    context = BookingContext(
        conversation_id="conversation-a",
        state=BookingState.SELECTING_SHOP,
    )
    container.memory_cache._contexts[context.conversation_id] = context
    resolver = StaticResolver(
        EntityResolutionResult(
            status=EntityResolutionStatus.RESOLVED,
            entity_kind=NLUEntityKind.SHOP,
            dispatch_intent="select_store",
            dispatch_payload={"shop": SHOP},
            matched_count=1,
        )
    )
    container.entity_resolution_coordinator = cast(
        EntityResolutionCoordinator,
        resolver,
    )

    response = post_message(
        client,
        conversation_id="conversation-a",
        message="Shibuya",
    )

    assert response.status_code == 200
    assert response.json()["state"] == "selecting_date"
    assert context.shop is SHOP
    assert resolver.calls == 1
    assert outbound_requests == []


def test_ambiguous_entity_returns_names_without_state_mutation(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = chat_client
    container = container_of(client)
    context = BookingContext(
        conversation_id="conversation-a",
        state=BookingState.SELECTING_SHOP,
    )
    container.memory_cache._contexts[context.conversation_id] = context
    candidates = tuple(
        EntityCandidate(
            kind=NLUEntityKind.SHOP,
            display_name=name,
            selection_key=f"shop:{index}",
        )
        for index, name in enumerate(("Shibuya", "Shinjuku", "Ginza"))
    )
    resolver = StaticResolver(
        EntityResolutionResult(
            status=EntityResolutionStatus.AMBIGUOUS,
            entity_kind=NLUEntityKind.SHOP,
            dispatch_intent=None,
            dispatch_payload={},
            candidates=candidates,
            matched_count=3,
        )
    )
    container.entity_resolution_coordinator = cast(
        EntityResolutionCoordinator,
        resolver,
    )

    response = post_message(
        client,
        conversation_id="conversation-a",
        message="Tokyo",
    )

    body = response.json()
    assert response.status_code == 200
    assert body["quick_replies"] == ["Shibuya", "Shinjuku", "Ginza"]
    assert body["state"] == "selecting_shop"
    assert context.state is BookingState.SELECTING_SHOP
    assert "shop:" not in response.text
    assert outbound_requests == []


def test_unknown_message_returns_state_aware_clarification(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, _ = chat_client
    container = container_of(client)
    context = BookingContext(
        conversation_id="conversation-a",
        state=BookingState.COMPLETED,
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id="conversation-a",
        message="nội dung không xác định",
    )

    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    assert "nhập lại rõ hơn" in response.json()["text"]


def test_response_never_exposes_sensitive_context_fields(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, _ = chat_client
    container = container_of(client)
    context = BookingContext(
        conversation_id="conversation-a",
        state=BookingState.BOOKING_FAILED,
        phone="0901234567",
        pending_action="internal_action",
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_message(
        client,
        conversation_id="conversation-a",
        message="unknown payload",
        idempotency_key="private-key",
    )
    body = response.json()
    serialized = response.text

    assert set(body) == {
        "conversation_id",
        "text",
        "state",
        "status",
        "instruction_template",
        "quick_replies",
        "metadata",
    }
    assert "0901234567" not in serialized
    assert "private-key" not in serialized
    assert "internal_action" not in serialized


def test_invalid_cached_context_maps_to_generic_500(
    chat_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, _ = chat_client
    container = container_of(client)
    container.memory_cache._contexts["conversation-a"] = cast(
        BookingContext,
        object(),
    )

    response = post_message(
        client,
        conversation_id="conversation-a",
        message="hello",
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
