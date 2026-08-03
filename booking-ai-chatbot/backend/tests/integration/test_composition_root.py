"""Integration tests for the complete in-process application object graph."""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from app.application.handlers.check_availability_handler import CheckAvailabilityHandler
from app.application.handlers.confirm_phone_handler import ConfirmPhoneHandler
from app.application.ports.booking_gateway import BookingGateway
from app.core.config import Settings
from app.dependencies import create_application_container
from app.dialog.dialog_controller import DialogTurnInput, DialogTurnStatus
from app.dialog.instruction_builder import DialogResponseDraft
from app.dialog.tool_bridge import ActionExecutionContext, ActionResult
from app.domain.booking import Service, Shop
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.booking_api.http_booking_gateway import HTTPBookingGateway
from app.infrastructure.cache.memory_cache import MemoryCache
from app.infrastructure.llm.openrouter_llm_gateway import OpenRouterLLMGateway

REQUIRED_ACTIONS = {
    "search_shop",
    "handle_store_selection",
    "handle_date_selection",
    "handle_people_selection",
    "handle_duration_selection",
    "handle_service_selection",
    "load_time_slots",
    "handle_time_selection",
    "handle_therapist_selection",
    "skip_therapist",
    "skip_therapist_for_group",
    "handle_phone_collection",
    "validate_phone",
    "mark_phone_confirmed",
    "create_booking",
    "retry_booking",
}

SHOP = Shop(
    shop_id=UUID("11111111-1111-1111-1111-111111111111"),
    name="Shibuya",
    address="Tokyo",
)
SERVICE = Service(
    service_id=UUID("22222222-2222-2222-2222-222222222222"),
    name="Aromatherapy",
    duration_minutes=60,
    price=Decimal("500000.00"),
)


class FailingAvailabilityHandler(CheckAvailabilityHandler):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, context: BookingContext) -> tuple[time, ...]:
        self.calls += 1
        context.set_available_slots((time(11, 0),))
        raise RuntimeError("POS unavailable")


def shop_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={
            "data": [
                {
                    "shop_id": str(SHOP.shop_id),
                    "shop_code": "SHOP001",
                    "name": SHOP.name,
                    "address": SHOP.address,
                    "phone": None,
                    "links": {
                        "self": f"/api/shops/{SHOP.shop_id}",
                        "courses": f"/api/shops/{SHOP.shop_id}/courses",
                        "available_slots": (
                            f"/api/shops/{SHOP.shop_id}/available-slots"
                        ),
                    },
                }
            ],
            "meta": {"total": 1, "limit": None, "next_cursor": None},
        },
    )


def settings() -> Settings:
    return Settings(pos_base_url="http://pos.test")


@pytest.mark.asyncio
async def test_container_assembles_shared_dependencies_without_network_calls() -> None:
    request_count = 0

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(unexpected_request),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)

    assert isinstance(container.booking_gateway, HTTPBookingGateway)
    gateway_handlers = tuple(
        handler
        for handler in container._handlers
        if not isinstance(handler, ConfirmPhoneHandler)
    )
    assert gateway_handlers
    assert all(
        handler._booking_gateway is container.booking_gateway  # type: ignore[attr-defined]
        for handler in gateway_handlers
    )
    assert REQUIRED_ACTIONS <= set(container.tool_bridge.registered_actions())
    assert container.state_machine._flow is container.flow_definition
    assert container.dialog_controller._flow is container.flow_definition
    assert container.dialog_controller._state_machine is container.state_machine
    assert container.dialog_controller._tool_bridge is container.tool_bridge
    assert isinstance(container.memory_cache, MemoryCache)
    assert container.conversation_context_store._cache is container.memory_cache
    assert container.instruction_builder.registered_templates()
    assert container.deterministic_nlu.parse(
        text="2 người",
        state=BookingState.SELECTING_PEOPLE,
    ).intent == "select_people"
    assert container.state_intent_policy.is_allowed(
        BookingState.SELECTING_PEOPLE,
        "select_people",
    )
    assert "*" not in container.state_intent_policy.allowed_for(BookingState.IDLE)
    assert container.entity_resolution_coordinator._search_shop_handler is (
        container._handlers[0]
    )
    assert container.entity_resolution_coordinator._search_service_handler is (
        container._handlers[1]
    )
    assert isinstance(container.llm_gateway, OpenRouterLLMGateway)
    assert container.llm_nlu_fallback._llm_gateway is container.llm_gateway
    assert container.llm_nlu_fallback._intent_policy is container.state_intent_policy
    assert container.faq_manager._knowledge_gateway is None
    assert container.faq_manager._instruction_builder is container.instruction_builder
    assert container.state_intent_policy.is_allowed(
        BookingState.IDLE,
        "ask_question",
    )
    assert container.state_intent_policy.is_allowed(
        BookingState.COMPLETED,
        "ask_question",
    )
    assert request_count == 0

    await container.close()
    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_two_containers_are_isolated_except_for_injected_client() -> None:
    client = httpx.AsyncClient()
    first = await create_application_container(settings(), http_client=client)
    second = await create_application_container(settings(), http_client=client)

    assert first.http_client is second.http_client
    assert first.booking_gateway is not second.booking_gateway
    assert first.dialog_controller is not second.dialog_controller
    assert first.tool_bridge is not second.tool_bridge
    assert first.state_machine is not second.state_machine
    assert first.flow_definition is not second.flow_definition
    assert first.memory_cache is not second.memory_cache
    assert first.conversation_context_store is not second.conversation_context_store
    assert first.conversation_context_store._cache is first.memory_cache
    assert second.conversation_context_store._cache is second.memory_cache
    assert first.instruction_builder is not second.instruction_builder
    assert first.deterministic_nlu is not second.deterministic_nlu
    assert first.state_intent_policy is not second.state_intent_policy
    assert (
        first.entity_resolution_coordinator
        is not second.entity_resolution_coordinator
    )
    assert first.llm_gateway is not second.llm_gateway
    assert first.llm_nlu_fallback is not second.llm_nlu_fallback
    assert first.faq_manager is not second.faq_manager
    assert first.llm_nlu_fallback._llm_gateway is first.llm_gateway
    assert second.llm_nlu_fallback._llm_gateway is second.llm_gateway

    async def custom_action(context: ActionExecutionContext) -> ActionResult:
        return ActionResult("container_only")

    first.tool_bridge.register_action("container_only", custom_action)
    first.instruction_builder.register_template(
        "container_only",
        lambda context, result: DialogResponseDraft("Chỉ container đầu."),
    )
    assert first.tool_bridge.has_action("container_only")
    assert not second.tool_bridge.has_action("container_only")
    assert first.instruction_builder.has_template("container_only")
    assert not second.instruction_builder.has_template("container_only")

    await first.close()
    await second.close()
    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_controller_reaches_people_state_with_only_one_shop_search() -> None:
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET" and request.url.path == "/api/shops":
            return shop_response(request)
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)
    context = BookingContext(conversation_id="conversation-1")

    start = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="start_booking", payload={}),
    )
    shop = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="select_store", payload={"shop": SHOP}),
    )
    booking_date = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(
            intent="select_date",
            payload={"booking_date": date(2099, 8, 5)},
        ),
    )

    assert start.status is DialogTurnStatus.SUCCESS
    assert start.executed_actions == ("search_shop",)
    assert shop.status is DialogTurnStatus.SUCCESS
    assert shop.executed_actions == ("handle_store_selection",)
    assert booking_date.status is DialogTurnStatus.SUCCESS
    assert booking_date.executed_actions == ("handle_date_selection",)
    assert context.state is BookingState.SELECTING_PEOPLE
    assert context.shop is SHOP
    assert context.booking_date == date(2099, 8, 5)
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/api/shops")
    ]

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_shop_search_failure_does_not_partially_mutate_context() -> None:
    requests: list[httpx.Request] = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, request=request)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(unavailable),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)
    context = BookingContext(
        conversation_id="conversation-1",
        pending_action="keep",
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="start_booking", payload={}),
    )

    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert result.failed_action == "search_shop"
    assert context.state is BookingState.IDLE
    assert context.shop is None
    assert context.pending_action == "keep"
    assert len(requests) == 1

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_phone_denial_uses_production_binding_and_commits_collection_state() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)
    context = BookingContext(
        conversation_id="conversation-phone",
        state=BookingState.VERIFYING_PHONE,
        shop=SHOP,
        service=SERVICE,
        booking_date=date(2099, 8, 5),
        start_time=time(10, 30),
        num_customer=1,
        duration_minutes=60,
        phone="0901234567",
        phone_confirmed=True,
        ng_list_checked=True,
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="deny", payload={}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.executed_actions == ("clear_phone_confirmation",)
    assert context.state is BookingState.COLLECTING_PHONE
    assert context.phone is None
    assert context.shop is SHOP
    assert context.service is SERVICE
    assert context.start_time == time(10, 30)

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_reload_failure_rolls_back_and_does_not_commit_selecting_time() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
        base_url="http://pos.test",
    )
    container = await create_application_container(settings(), http_client=client)
    handler = FailingAvailabilityHandler()
    container.tool_bridge._check_availability_handler = handler
    stale_slots = (time(9, 0),)
    context = BookingContext(
        conversation_id="conversation-reload-failure",
        state=BookingState.BOOKING_FAILED,
        shop=SHOP,
        service=SERVICE,
        booking_date=date(2099, 8, 5),
        start_time=time(9, 0),
        num_customer=1,
        duration_minutes=60,
        available_slots=stale_slots,
    )

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="select_time", payload={}),
    )

    assert result.status is DialogTurnStatus.FAILURE_UNHANDLED
    assert result.failed_action == "reload_time_slots"
    assert handler.calls == 1
    assert context.state is BookingState.BOOKING_FAILED
    assert context.available_slots == stale_slots
    assert context.start_time == time(9, 0)
    assert context.booking is None

    await container.close()
    await client.aclose()


def accepts_booking_gateway(gateway: BookingGateway) -> BookingGateway:
    """Provide a static Protocol assignment checked by mypy."""
    return gateway


@pytest.mark.asyncio
async def test_http_gateway_satisfies_booking_gateway_protocol_statically() -> None:
    client = httpx.AsyncClient()
    gateway = HTTPBookingGateway(client=client, base_url="http://pos.test")

    assert accepts_booking_gateway(gateway) is gateway
    await client.aclose()
