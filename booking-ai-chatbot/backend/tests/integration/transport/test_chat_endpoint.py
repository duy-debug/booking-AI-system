"""Integration tests for the non-streaming FastAPI chat endpoint."""

import json
from collections.abc import Iterator
from datetime import date, time
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.dependencies as dependencies
from app.application.ports.knowledge_gateway import KnowledgeDocument
from app.application.ports.llm_gateway import LLMMessage, LLMResponse
from app.core.config import Settings
from app.dependencies import ApplicationContainer
from app.dialog.entity_resolution import (
    EntityCandidate,
    EntityResolutionCoordinator,
    EntityResolutionResult,
    EntityResolutionStatus,
)
from app.dialog.nlu import (
    DeterministicNLU,
    LLMNLUFallback,
    NLUEntityKind,
    NLUResolutionStatus,
    NLUResult,
    NLUSource,
)
from app.dialog.tool_bridge import ActionExecutionContext, ActionResult
from app.domain.booking import Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.main import create_app

SHOP = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Shibuya",
    address="Tokyo",
)


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

        async def search_shop_action(
            context: ActionExecutionContext,
        ) -> ActionResult:
            return ActionResult("search_shop")

        async def load_service_catalog_action(
            context: ActionExecutionContext,
        ) -> ActionResult:
            return ActionResult("load_service_catalog")

        container.tool_bridge.register_action("search_shop", search_shop_action)
        container.tool_bridge.register_action(
            "load_service_catalog",
            load_service_catalog_action,
        )
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
    assert set(application.openapi()["paths"]) == {
        "/api/v1/chat",
        "/api/v1/chat/stream",
    }
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
    container.deterministic_nlu = cast(DeterministicNLU, AlwaysUnresolvedNLU())
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
    container.knowledge_gateway = gateway

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
