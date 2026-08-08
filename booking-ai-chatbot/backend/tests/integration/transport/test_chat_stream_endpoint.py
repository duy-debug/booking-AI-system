"""Integration tests for the business-event SSE chat endpoint."""

import json
from collections.abc import Iterator
from datetime import date, time
from decimal import Decimal
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.dependencies as dependencies
from app.application.handlers.check_availability_handler import CheckAvailabilityHandler
from app.application.handlers.create_booking_handler import CreateBookingHandler
from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dependencies import ApplicationContainer
from app.dialog.nlu import (
    LLMNLU,
    EntityCandidate,
    EntityResolutionCoordinator,
    EntityResolutionResult,
    EntityResolutionStatus,
    NLUEntityKind,
    NLUResult,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_models import (
    Booking,
    BookingGateway,
    Course,
    CreateBookingRequest,
    CreateBookingResult,
    Customer,
    FinalAvailabilityRequest,
    FinalAvailabilityResult,
    Shop,
)
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome, HandlerResult
from app.infrastructure.context_store import Settings
from app.infrastructure.gemini_client import (
    LLMGatewayUnavailableError,
    LLMMessage,
    LLMResponse,
)
from app.infrastructure.qdrant_client import (
    FAQManager,
    KnowledgeDocument,
    KnowledgeGatewayUnavailableError,
)
from app.main import create_app
from tests.structured_nlu_gateway import StructuredNLUGateway

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


class RecordingSearchShopHandler(SearchShopHandler):
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    async def execute(
        self,
        query: str | None = None,
        *,
        criteria: object | None = None,
    ) -> HandlerResult:
        self.calls.append(query)
        return HandlerResult(HandlerOutcome.SUCCESS, {"shops": (SHOP,)})


class RecordingAvailabilityHandler(CheckAvailabilityHandler):
    def __init__(self) -> None:
        self.calls: list[BookingContext] = []
        self.slots = (time(10, 30), time(11, 0))

    async def execute(self, context: BookingContext) -> HandlerResult:
        self.calls.append(context)
        return HandlerResult(
            HandlerOutcome.SUCCESS,
            {"slots": self.slots},
            {"available_slots": self.slots},
        )


class EndpointCreateGateway:
    def __init__(self) -> None:
        self.final_requests: list[FinalAvailabilityRequest] = []
        self.create_requests: list[CreateBookingRequest] = []

    async def check_final_availability(
        self,
        request: FinalAvailabilityRequest,
    ) -> FinalAvailabilityResult:
        self.final_requests.append(request)
        return FinalAvailabilityResult(available=True)

    async def create_booking(
        self,
        request: CreateBookingRequest,
    ) -> CreateBookingResult:
        self.create_requests.append(request)
        booking = Booking(
            booking_id=UUID("33333333-3333-3333-3333-333333333333"),
            status="confirmed",
            shop=SHOP,
            main_course=COURSE,
            customer=Customer(request.phone, request.customer_name),
            booking_date=request.booking_date,
            start_time=request.start_time,
            num_customer=request.num_customer,
            duration_minutes=request.duration_minutes,
        )
        return CreateBookingResult(booking)


class StaticResolver:
    def __init__(self, result: EntityResolutionResult) -> None:
        self.result = result

    async def resolve(
        self,
        *,
        nlu_result: NLUResult,
        state: BookingState,
        context: BookingContext,
    ) -> EntityResolutionResult:
        return self.result


class FailingNLU:
    async def parse(
        self,
        *,
        text: str,
        state: BookingState,
        context: BookingContext | None = None,
    ) -> NLUResult:
        raise RuntimeError("private runtime failure")


class StaticLLMGateway:
    def __init__(
        self,
        content: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self.error = error
        self.calls = 0

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return LLMResponse(content=self.content)


class StaticKnowledgeGateway:
    def __init__(
        self,
        documents: list[KnowledgeDocument] | None = None,
        error: KnowledgeGatewayUnavailableError | None = None,
    ) -> None:
        self.documents = documents or []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeDocument]:
        self.calls.append((query, limit))
        if self.error is not None:
            raise self.error
        return self.documents


@pytest.fixture
def stream_client(
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
        container.llm_nlu = LLMNLU(
            llm_gateway=StructuredNLUGateway(),
            intent_policy=container.state_intent_policy,
        )
        container.action_registry._search_shop_handler = RecordingSearchShopHandler()
        yield client, outbound_requests


def container_of(client: TestClient) -> ApplicationContainer:
    application = cast(FastAPI, client.app)
    return cast(ApplicationContainer, application.state.application_container)


def post_stream(
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
    return cast(httpx.Response, client.post("/api/v1/chat/stream", json=payload))


def parse_events(response: httpx.Response) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for frame in response.text.strip().split("\n\n"):
        lines = frame.split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        assert isinstance(data, dict)
        events.append((event, data))
    return events


def test_stream_success_contract_and_event_order(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client
    application = cast(FastAPI, client.app)

    response = post_stream(
        client,
        conversation_id="conversation-a",
        message="Tôi muốn đặt lịch",
    )
    events = parse_events(response)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert [event for event, _ in events] == ["started", "message", "completed"]
    assert events[0][1] == {"conversation_id": "conversation-a"}
    assert set(events[1][1]) == {
        "conversation_id",
        "text",
        "state",
        "status",
        "instruction_template",
        "quick_replies",
        "metadata",
    }
    assert events[2][1]["stream_status"] == "completed"
    assert events[-1][0] == "completed"
    assert "token" not in {event for event, _ in events}
    assert set(application.openapi()["paths"]) == {
        "/api/v1/chat",
        "/api/v1/chat/stream",
    }
    search = cast(
        RecordingSearchShopHandler,
        container_of(client).action_registry._search_shop_handler,
    )
    assert search.calls == [None]
    assert outbound_requests == []


def test_change_request_has_json_parity_and_normal_sse_event_order(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client
    container = container_of(client)
    context = BookingContext(
        "conversation-change",
        state=BookingState.AWAITING_CONFIRMATION,
        booking_date=date(2026, 8, 5),
        start_time=time(10, 0),
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_stream(
        client,
        conversation_id=context.conversation_id,
        message="đổi ngày",
    )
    events = parse_events(response)

    assert response.status_code == 200
    assert [event for event, _ in events] == ["started", "message", "completed"]
    assert events[1][1]["state"] == "selecting_date"
    assert events[1][1]["text"] == "Bạn muốn đổi sang ngày nào?"
    assert "token" not in {event for event, _ in events}
    saved = container.memory_cache._contexts[context.conversation_id]
    assert saved.booking_date is None
    assert saved.start_time is None
    assert outbound_requests == []


def test_p2_recovery_keeps_sse_order_and_json_parity(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client
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
    container.llm_nlu = LLMNLU(
        llm_gateway=gateway,
        intent_policy=container.state_intent_policy,
    )
    context = BookingContext(
        "conversation-p2-stream",
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

    response = post_stream(
        client,
        conversation_id=context.conversation_id,
        message="10:30",
    )
    events = parse_events(response)

    assert response.status_code == 200
    assert [event for event, _ in events] == ["started", "message", "completed"]
    assert events[1][1]["status"] == "success"
    assert events[1][1]["state"] == "selecting_time"
    assert len(availability.calls) == 1
    assert availability.calls[0].conversation_id == context.conversation_id
    saved = container.memory_cache._contexts[context.conversation_id]
    assert saved.available_slots == availability.slots
    assert saved.start_time == time(9, 0)
    assert saved.booking is None
    assert gateway.calls == 1
    assert outbound_requests == []


def test_completed_booking_without_code_has_json_sse_parity_and_one_create_per_request(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client
    container = container_of(client)
    gateway = EndpointCreateGateway()
    container.action_registry._create_booking_handler = CreateBookingHandler(
        cast(BookingGateway, gateway)
    )

    def ready_context(conversation_id: str) -> BookingContext:
        return BookingContext(
            conversation_id,
            state=BookingState.AWAITING_CONFIRMATION,
            shop=SHOP,
            main_course=COURSE,
            customer=Customer("0901234567", "Nguyen An"),
            booking_date=date(2099, 8, 15),
            start_time=time(10, 30),
            num_customer=1,
            duration_minutes=60,
            phone="0901234567",
            phone_confirmed=True,
            ng_list_checked=True,
        )

    json_context = ready_context("conversation-e2e-json")
    sse_context = ready_context("conversation-e2e-sse")
    container.memory_cache._contexts[json_context.conversation_id] = json_context
    container.memory_cache._contexts[sse_context.conversation_id] = sse_context

    regular = client.post(
        "/api/v1/chat",
        json={
            "conversation_id": json_context.conversation_id,
            "message": "xác nhận",
            "idempotency_key": "endpoint-json",
        },
    )
    streamed = post_stream(
        client,
        conversation_id=sse_context.conversation_id,
        message="xác nhận",
        idempotency_key="endpoint-sse",
    )
    events = parse_events(streamed)

    assert regular.status_code == 200
    assert regular.json()["state"] == "completed"
    assert regular.json()["status"] == "success"
    assert regular.json()["metadata"] == {"booking_created": True}
    completion_text = cast(str, regular.json()["text"])
    assert "Đặt lịch thành công" in completion_text
    assert "đã được ghi nhận" in completion_text
    assert "Mã đặt lịch" not in completion_text
    assert "booking code" not in completion_text.casefold()
    assert "reservation code" not in completion_text.casefold()
    assert str(json_context.booking_id) not in completion_text
    assert [event for event, _ in events] == ["started", "message", "completed"]
    assert events[1][1]["state"] == regular.json()["state"]
    assert events[1][1]["status"] == regular.json()["status"]
    assert events[1][1]["text"] == regular.json()["text"]
    assert events[1][1]["metadata"] == regular.json()["metadata"]
    assert len(gateway.final_requests) == 2
    assert len(gateway.create_requests) == 2
    attempt_ids = {request.idempotency_key for request in gateway.create_requests}
    assert len(attempt_ids) == 2
    assert "endpoint-json" not in attempt_ids
    assert "endpoint-sse" not in attempt_ids
    assert outbound_requests == []


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "hello"},
        {"conversation_id": "conversation-a", "message": " "},
        {
            "conversation_id": "conversation-a",
            "message": "hello",
            "idempotency_key": "",
        },
    ],
)
def test_invalid_request_returns_422_before_streaming(
    stream_client: tuple[TestClient, list[httpx.Request]],
    payload: dict[str, str],
) -> None:
    client, _ = stream_client

    response = client.post("/api/v1/chat/stream", json=payload)

    assert response.status_code == 422
    assert "text/event-stream" not in response.headers["content-type"]
    assert "event: started" not in response.text


def test_unknown_input_is_a_normal_message_not_an_error(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, _ = stream_client
    container = container_of(client)
    gateway = StaticLLMGateway(error=LLMGatewayUnavailableError("provider unavailable"))
    container.llm_nlu = LLMNLU(
        llm_gateway=gateway,
        intent_policy=container.state_intent_policy,
    )
    context = BookingContext(
        conversation_id="conversation-a",
        state=BookingState.COMPLETED,
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_stream(
        client,
        conversation_id="conversation-a",
        message="nội dung không xác định",
    )
    events = parse_events(response)

    assert [event for event, _ in events] == ["started", "message", "completed"]
    assert events[1][1]["state"] == "completed"
    assert "nhập lại rõ hơn" in cast(str, events[1][1]["text"])
    assert gateway.calls == 1


def test_ambiguous_entity_is_streamed_as_a_normal_message(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client
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
        for index, name in enumerate(("Shibuya", "Shinjuku"))
    )
    container.entity_resolution_coordinator = cast(
        EntityResolutionCoordinator,
        StaticResolver(
            EntityResolutionResult(
                status=EntityResolutionStatus.AMBIGUOUS,
                entity_kind=NLUEntityKind.SHOP,
                dispatch_intent=None,
                dispatch_payload={},
                candidates=candidates,
                matched_count=2,
            )
        ),
    )

    response = post_stream(
        client,
        conversation_id="conversation-a",
        message="Tokyo",
    )
    events = parse_events(response)

    assert [event for event, _ in events] == ["started", "message", "completed"]
    assert events[1][1]["quick_replies"] == ["Shibuya", "Shinjuku"]
    assert context.state is BookingState.SELECTING_SHOP
    assert outbound_requests == []


def test_runtime_processing_error_becomes_terminal_safe_error_event(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, _ = stream_client
    container = container_of(client)
    container.llm_nlu = cast(LLMNLU, FailingNLU())

    response = post_stream(
        client,
        conversation_id="conversation-a",
        message="private raw message",
    )
    events = parse_events(response)

    assert response.status_code == 200
    assert [event for event, _ in events] == ["started", "error"]
    assert events[1][1] == {
        "conversation_id": "conversation-a",
        "code": "chat_processing_failed",
        "message": "Hệ thống chưa thể xử lý yêu cầu lúc này.",
    }
    assert "private runtime failure" not in response.text
    assert "event: completed" not in response.text


def test_stream_payload_does_not_expose_sensitive_context_or_request_data(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, _ = stream_client
    container = container_of(client)
    internal_id = UUID("99999999-9999-9999-9999-999999999999")
    context = BookingContext(
        conversation_id="conversation-a",
        state=BookingState.COMPLETED,
        phone="0901234567",
        booking_id=internal_id,
        last_failure_code="private_action",
    )
    container.memory_cache._contexts[context.conversation_id] = context

    response = post_stream(
        client,
        conversation_id="conversation-a",
        message="private raw message",
        idempotency_key="private-key",
    )

    assert "private raw message" not in response.text
    assert "0901234567" not in response.text
    assert str(internal_id) not in response.text
    assert "private-key" not in response.text
    assert "private_action" not in response.text


def test_context_is_retained_between_stream_and_json_requests(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client

    streamed = post_stream(
        client,
        conversation_id="conversation-a",
        message="Tôi muốn đặt lịch",
    )
    regular = client.post(
        "/api/v1/chat",
        json={
            "conversation_id": "conversation-a",
            "message": "Tokyo",
        },
    )
    context = container_of(client).memory_cache._contexts["conversation-a"]

    assert streamed.status_code == regular.status_code == 200
    assert parse_events(streamed)[1][1]["state"] == "selecting_shop"
    assert regular.json()["state"] == "selecting_shop"
    assert context.state is BookingState.SELECTING_SHOP
    assert len(outbound_requests) == 1
    assert outbound_requests[0].url.path == "/api/shops"


def test_stream_message_has_parity_with_json_on_independent_contexts(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client
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
    container.llm_nlu = LLMNLU(
        llm_gateway=gateway,
        intent_policy=container.state_intent_policy,
    )

    regular = client.post(
        "/api/v1/chat",
        json={
            "conversation_id": "conversation-json",
            "message": "Tôi muốn đặt lịch",
        },
    )
    streamed = post_stream(
        client,
        conversation_id="conversation-sse",
        message="Tôi muốn đặt lịch",
    )
    regular_body = regular.json()
    stream_message = parse_events(streamed)[1][1]

    assert regular.status_code == streamed.status_code == 200
    for key in {
        "text",
        "state",
        "status",
        "instruction_template",
        "quick_replies",
        "metadata",
    }:
        assert stream_message[key] == regular_body[key]
    assert stream_message["conversation_id"] == "conversation-sse"
    assert regular_body["conversation_id"] == "conversation-json"
    assert gateway.calls == 2
    assert outbound_requests == []


def test_faq_stream_has_json_parity_and_uses_one_injected_gateway(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client
    container = container_of(client)
    gateway = StaticKnowledgeGateway(
        [KnowledgeDocument("Bãi đỗ xe nằm cạnh cửa hàng.", 0.9, "private")]
    )
    container.faq_manager = FAQManager(
        knowledge_gateway=gateway,
        instruction_builder=container.instruction_builder,
    )
    message = "Có chỗ đậu xe không?"

    regular = client.post(
        "/api/v1/chat",
        json={"conversation_id": "faq-json", "message": message},
    )
    streamed = post_stream(
        client,
        conversation_id="faq-sse",
        message=message,
    )
    events = parse_events(streamed)
    regular_body = regular.json()
    stream_message = events[1][1]

    assert [event for event, _ in events] == ["started", "message", "completed"]
    for key in {
        "text",
        "state",
        "status",
        "instruction_template",
        "quick_replies",
        "metadata",
    }:
        assert stream_message[key] == regular_body[key]
    assert gateway.calls == [(message, 3), (message, 3)]
    assert "token" not in {event for event, _ in events}
    assert outbound_requests == []


def test_handled_knowledge_failure_is_a_normal_sse_message(
    stream_client: tuple[TestClient, list[httpx.Request]],
) -> None:
    client, outbound_requests = stream_client
    gateway = StaticKnowledgeGateway(
        error=KnowledgeGatewayUnavailableError("private provider failure")
    )
    container = container_of(client)
    container.faq_manager = FAQManager(
        knowledge_gateway=gateway,
        instruction_builder=container.instruction_builder,
    )

    response = post_stream(
        client,
        conversation_id="faq-unavailable",
        message="Chính sách hủy lịch như thế nào?",
    )
    events = parse_events(response)

    assert [event for event, _ in events] == ["started", "message", "completed"]
    assert events[1][1]["status"] == "failure_handled"
    assert events[1][1]["metadata"] == {
        "response_type": "faq",
        "source_count": 0,
    }
    assert "private provider failure" not in response.text
    assert "error" not in {event for event, _ in events}
    assert outbound_requests == []
