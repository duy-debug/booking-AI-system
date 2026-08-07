"""Integration tests for Gemini NLU inside the shared chat pipeline."""

import json
from collections.abc import AsyncIterator
from datetime import date
from typing import cast

import httpx
import pytest

from app.application.handlers.search_shop_handler import SearchShopHandler
from app.dependencies import ApplicationContainer, create_application_container
from app.dialog.dialog_controller import DialogController, DialogTurnInput, DialogTurnResult
from app.dialog.nlu import (
    EntityResolutionCoordinator,
    EntityResolutionResult,
    EntityResolutionStatus,
    NLUEntityKind,
    NLUResult,
)
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.domain.outcomes import HandlerOutcome, HandlerResult
from app.infrastructure.context_store import Settings
from app.infrastructure.gemini_client import (
    LLMGatewayUnavailableError,
    LLMMessage,
    LLMResponse,
)
from app.transport.chat_api import _process_chat_message
from app.transport.schemas import ChatRequest


class FakeLLMGateway:
    def __init__(self) -> None:
        self.content: str | None = None
        self.error: Exception | None = None
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


class FakeSearchShopHandler(SearchShopHandler):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, query: str | None = None) -> HandlerResult:
        self.calls += 1
        return HandlerResult(HandlerOutcome.SUCCESS, {"shops": ()})


class ControllerSpy:
    def __init__(self, delegate: DialogController) -> None:
        self.delegate = delegate
        self.calls: list[DialogTurnInput] = []

    async def handle_turn(
        self,
        context: BookingContext,
        turn: DialogTurnInput,
    ) -> DialogTurnResult:
        self.calls.append(turn)
        return await self.delegate.handle_turn(context, turn)

    async def handle_message(
        self,
        *,
        conversation_id: str,
        message: str,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> object:
        return await self.delegate.handle_message(
            conversation_id=conversation_id,
            message=message,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )


class ResolverSpy:
    def __init__(self) -> None:
        self.calls: list[NLUResult] = []

    async def resolve(
        self,
        *,
        nlu_result: NLUResult,
        state: BookingState,
        context: BookingContext,
    ) -> EntityResolutionResult:
        self.calls.append(nlu_result)
        return EntityResolutionResult(
            status=EntityResolutionStatus.NOT_FOUND,
            entity_kind=cast(NLUEntityKind, nlu_result.entity_kind),
            dispatch_intent=None,
            dispatch_payload={},
            failure_code="not_found",
        )


@pytest.fixture
async def runtime() -> AsyncIterator[
    tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]]
]:
    requests: list[httpx.Request] = []

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(unexpected_request),
        base_url="http://pos.test",
    )
    gateway = FakeLLMGateway()
    container = await create_application_container(
        Settings(pos_base_url="http://pos.test"),
        http_client=client,
        llm_gateway=gateway,
    )
    yield container, gateway, requests
    await container.close()
    await client.aclose()


def output(
    intent: str,
    *,
    confidence: float = 0.9,
    entities: dict[str, object] | None = None,
    entity_kind: str | None = None,
    entity_query: str | None = None,
) -> str:
    return json.dumps(
        {
            "intent": intent,
            "confidence": confidence,
            "entities": entities or {},
            "entity_kind": entity_kind,
            "entity_query": entity_query,
        }
    )


def request(message: str) -> ChatRequest:
    return ChatRequest(conversation_id="conversation-a", message=message)


def spy_controller(container: ApplicationContainer) -> ControllerSpy:
    spy = ControllerSpy(container.dialog_controller)
    container.dialog_controller = cast(DialogController, spy)
    return spy


@pytest.mark.asyncio
async def test_start_booking_uses_llm_once(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
) -> None:
    container, gateway, external_requests = runtime

    search_shop = FakeSearchShopHandler()
    container.action_registry._search_shop_handler = search_shop
    gateway.content = output("start_booking")

    response = await _process_chat_message(
        request=request("Tôi muốn đặt lịch"),
        container=container,
    )

    assert gateway.calls == 1
    assert search_shop.calls == 1
    assert response.state is BookingState.SELECTING_SHOP
    assert external_requests == []


@pytest.mark.asyncio
async def test_entity_query_uses_llm_once(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
) -> None:
    container, gateway, external_requests = runtime
    context = await container.conversation_context_store.get_copy("conversation-a")
    context.state = BookingState.SELECTING_SHOP
    await container.conversation_context_store.save("conversation-a", context)
    gateway.content = output(
        "select_shop",
        entity_kind="shop",
        entity_query="Tokyo",
    )

    response = await _process_chat_message(
        request=request("Tokyo"),
        container=container,
    )

    assert gateway.calls == 1
    assert response.state is BookingState.SELECTING_SHOP
    assert len(external_requests) == 1
    assert external_requests[0].url.path == "/api/shops"


@pytest.mark.asyncio
async def test_change_request_uses_llm_once(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
) -> None:
    container, gateway, external_requests = runtime
    context = await container.conversation_context_store.get_copy("conversation-a")
    context.state = BookingState.AWAITING_CONFIRMATION
    context.booking_date = date(2026, 8, 5)
    await container.conversation_context_store.save("conversation-a", context)
    gateway.content = output(
        "change_info",
        entities={"change_target": "date"},
    )

    response = await _process_chat_message(
        request=request("đổi ngày"),
        container=container,
    )

    assert gateway.calls == 1
    assert response.state is BookingState.SELECTING_DATE
    stored = await container.conversation_context_store.get_copy("conversation-a")
    assert stored.booking_date is None
    assert external_requests == []


@pytest.mark.asyncio
async def test_unresolved_then_valid_people_output_runs_one_controller_turn(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
) -> None:
    container, gateway, external_requests = runtime
    controller = spy_controller(container)
    context = await container.conversation_context_store.get_copy("conversation-a")
    context.state = BookingState.SELECTING_PEOPLE
    await container.conversation_context_store.save("conversation-a", context)
    gateway.content = output(
        "select_people",
        entities={"number_of_people": 3},
    )

    response = await _process_chat_message(
        request=request("Mai tôi đi cùng hai người bạn"),
        container=container,
    )

    assert gateway.calls == 1
    assert len(controller.calls) == 1
    assert controller.calls[0].payload == {"num_customer": 3}
    stored = await container.conversation_context_store.get_copy("conversation-a")
    assert stored.num_customer == 3
    assert stored.state is BookingState.SELECTING_DURATION
    assert response.state is BookingState.SELECTING_DURATION
    assert external_requests == []


@pytest.mark.asyncio
async def test_composed_llm_nlu_routes_unknown_text_to_safe_recovery(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
) -> None:
    container, gateway, external_requests = runtime
    controller = spy_controller(container)
    context = await container.conversation_context_store.get_copy("conversation-a")
    context.state = BookingState.SELECTING_DURATION
    await container.conversation_context_store.save("conversation-a", context)
    gateway.content = output(
        "select_duration",
        entities={"duration_minutes": 60},
    )

    response = await _process_chat_message(
        request=request("Khoang mot tieng"),
        container=container,
    )

    assert gateway.calls == 1
    assert len(controller.calls) == 1
    assert controller.calls[0].payload == {"duration_minutes": 60}
    stored = await container.conversation_context_store.get_copy("conversation-a")
    assert stored.duration_minutes == 60
    assert stored.state is BookingState.SELECTING_SERVICE
    assert response.state is BookingState.SELECTING_SERVICE
    assert external_requests == []


@pytest.mark.asyncio
async def test_llm_shop_query_goes_through_entity_resolver_without_domain_object(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
) -> None:
    container, gateway, external_requests = runtime
    resolver = ResolverSpy()
    container.entity_resolution_coordinator = cast(EntityResolutionCoordinator, resolver)
    context = await container.conversation_context_store.get_copy("conversation-a")
    context.state = BookingState.SELECTING_SHOP
    await container.conversation_context_store.save("conversation-a", context)
    gateway.content = output(
        "select_shop",
        entity_kind="shop",
        entity_query="quận 1",
    )

    response = await _process_chat_message(
        request=request("Tôi muốn tới chi nhánh gần quận 1"),
        container=container,
    )

    assert gateway.calls == 1
    assert len(resolver.calls) == 1
    assert resolver.calls[0].entity_kind is NLUEntityKind.SHOP
    assert resolver.calls[0].entity_query == "quận 1"
    assert resolver.calls[0].payload == {}
    assert context.shop is None
    assert "Không tìm thấy cửa hàng" in response.text
    assert external_requests == []


@pytest.mark.asyncio
async def test_state_disallowed_llm_intent_returns_clarification_without_controller(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
) -> None:
    container, gateway, external_requests = runtime
    controller = spy_controller(container)
    context = await container.conversation_context_store.get_copy("conversation-a")
    context.state = BookingState.SELECTING_PEOPLE
    await container.conversation_context_store.save("conversation-a", context)
    gateway.content = output("confirm")

    response = await _process_chat_message(
        request=request("Ok chốt giúp mình"),
        container=container,
    )

    assert gateway.calls == 1
    assert controller.calls == []
    assert context.state is BookingState.SELECTING_PEOPLE
    assert context.num_customer is None
    assert "số người từ 1 đến 3" in response.text
    assert external_requests == []


@pytest.mark.asyncio
async def test_multiple_llm_entities_apply_current_and_future_state_entities(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
) -> None:
    container, gateway, external_requests = runtime
    controller = spy_controller(container)
    context = await container.conversation_context_store.get_copy("conversation-a")
    context.state = BookingState.SELECTING_PEOPLE
    await container.conversation_context_store.save("conversation-a", context)
    gateway.content = output(
        "select_people",
        entities={
            "number_of_people": 3,
            "booking_date": "2026-08-03",
            "duration_minutes": 60,
        },
    )

    await _process_chat_message(
        request=request("Mai tôi đi cùng hai người bạn"),
        container=container,
    )

    assert gateway.calls == 1
    assert len(controller.calls) == 2
    assert controller.calls[0].payload == {"num_customer": 3}
    assert controller.calls[1].payload == {"duration_minutes": 60}
    saved = await container.conversation_context_store.get_copy("conversation-a")
    assert saved.booking_date is None
    assert saved.duration_minutes == 60
    assert saved.state is BookingState.SELECTING_SERVICE
    assert external_requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "error"),
    [
        (output("select_people", confidence=0.5, entities={"number_of_people": 2}), None),
        (None, LLMGatewayUnavailableError("provider unavailable")),
    ],
)
async def test_low_confidence_or_provider_failure_is_safe_and_non_mutating(
    runtime: tuple[ApplicationContainer, FakeLLMGateway, list[httpx.Request]],
    content: str | None,
    error: Exception | None,
) -> None:
    container, gateway, external_requests = runtime
    controller = spy_controller(container)
    context = await container.conversation_context_store.get_copy("conversation-a")
    context.state = BookingState.SELECTING_PEOPLE
    await container.conversation_context_store.save("conversation-a", context)
    gateway.content = content
    gateway.error = error

    response = await _process_chat_message(
        request=request("không rõ"),
        container=container,
    )

    assert gateway.calls == 1
    assert controller.calls == []
    assert context.state is BookingState.SELECTING_PEOPLE
    assert context.num_customer is None
    assert "số người từ 1 đến 3" in response.text
    assert external_requests == []
