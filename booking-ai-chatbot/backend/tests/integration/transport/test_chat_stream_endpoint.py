"""Integration tests for the business-event SSE chat endpoint."""

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
from app.application.ports.llm_gateway import (
    LLMGatewayUnavailableError,
    LLMMessage,
    LLMResponse,
)
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
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.main import create_app


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
    def parse(self, *, text: str, state: BookingState) -> NLUResult:
        raise RuntimeError("private runtime failure")


class AlwaysUnresolvedNLU:
    def parse(self, *, text: str, state: BookingState) -> NLUResult:
        return NLUResult(
            intent=None,
            payload={},
            confidence=0.0,
            source=NLUSource.FALLBACK,
            resolution_status=NLUResolutionStatus.UNRESOLVED,
        )


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

        async def search_shop_action(
            context: ActionExecutionContext,
        ) -> ActionResult:
            return ActionResult("search_shop")

        container.tool_bridge.register_action("search_shop", search_shop_action)
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
    assert context.booking_date is None
    assert context.start_time is None
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
    gateway = StaticLLMGateway(
        error=LLMGatewayUnavailableError("provider unavailable")
    )
    container.deterministic_nlu = cast(DeterministicNLU, AlwaysUnresolvedNLU())
    container.llm_nlu_fallback = LLMNLUFallback(
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
    container.deterministic_nlu = cast(DeterministicNLU, FailingNLU())

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
        pending_action="private_action",
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
    assert outbound_requests == []


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
    container.deterministic_nlu = cast(DeterministicNLU, AlwaysUnresolvedNLU())
    container.llm_nlu_fallback = LLMNLUFallback(
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
