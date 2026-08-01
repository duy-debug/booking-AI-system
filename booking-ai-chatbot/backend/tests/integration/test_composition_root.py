"""Integration tests for the complete in-process application object graph."""

import httpx
import pytest

from app.application.handlers.confirm_phone_handler import ConfirmPhoneHandler
from app.application.ports.booking_gateway import BookingGateway
from app.core.config import Settings
from app.dependencies import create_application_container
from app.dialog.dialog_controller import DialogTurnInput, DialogTurnStatus
from app.dialog.tool_bridge import ActionExecutionContext, ActionResult
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.booking_api.http_booking_gateway import HTTPBookingGateway
from app.infrastructure.cache.memory_cache import MemoryCache

REQUIRED_ACTIONS = {
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

    async def custom_action(context: ActionExecutionContext) -> ActionResult:
        return ActionResult("container_only")

    first.tool_bridge.register_action("container_only", custom_action)
    assert first.tool_bridge.has_action("container_only")
    assert not second.tool_bridge.has_action("container_only")

    await first.close()
    await second.close()
    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_controller_runs_non_pos_turn_without_reloading_or_network() -> None:
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

    async def search_shop_action(context: ActionExecutionContext) -> ActionResult:
        return ActionResult("search_shop", [])

    container.tool_bridge.register_action("search_shop", search_shop_action)
    context = BookingContext(conversation_id="conversation-1")

    result = await container.dialog_controller.handle_turn(
        context,
        DialogTurnInput(intent="start_booking", payload={}),
    )

    assert result.status is DialogTurnStatus.SUCCESS
    assert result.executed_actions == ("search_shop",)
    assert context.state is BookingState.SELECTING_SHOP
    assert request_count == 0

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
