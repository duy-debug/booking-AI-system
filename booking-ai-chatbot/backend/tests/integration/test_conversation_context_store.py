"""Integration tests for conversation-context lifecycle composition."""

from datetime import date

import httpx
import pytest

from app.core.config import Settings
from app.dependencies import create_application_container
from app.domain.booking_state import BookingState


def settings() -> Settings:
    return Settings(pos_base_url="http://pos.test")


@pytest.mark.asyncio
async def test_context_lifecycle_preserves_data_then_replaces_it_on_reset() -> None:
    request_count = 0

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(500, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request))
    container = await create_application_container(settings(), http_client=client)
    store = container.conversation_context_store

    context = await store.get_or_create("conversation-a")
    context.set_booking_date(date(2026, 8, 2))
    context.state = BookingState.SELECTING_PEOPLE
    await store.save("conversation-a", context)
    reloaded = await store.get_or_create("conversation-a")

    assert reloaded is context
    assert reloaded.booking_date == date(2026, 8, 2)
    assert reloaded.state is BookingState.SELECTING_PEOPLE

    reset_context = await store.reset("conversation-a")

    assert reset_context is not context
    assert reset_context.state is BookingState.IDLE
    assert reset_context.booking_date is None
    assert await store.get_or_create("conversation-a") is reset_context
    assert request_count == 0

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_conversations_are_isolated_in_the_same_store() -> None:
    client = httpx.AsyncClient()
    container = await create_application_container(settings(), http_client=client)
    store = container.conversation_context_store
    first = await store.get_or_create("conversation-a")
    second = await store.get_or_create("conversation-b")

    first.set_booking_date(date(2026, 8, 2))
    await store.save("conversation-a", first)

    assert second.booking_date is None
    assert await store.get_or_create("conversation-b") is second

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_container_store_uses_the_container_memory_cache() -> None:
    client = httpx.AsyncClient()
    container = await create_application_container(settings(), http_client=client)

    context = await container.conversation_context_store.get_or_create(
        "conversation-a"
    )

    assert container.conversation_context_store._cache is container.memory_cache
    assert await container.memory_cache.get("conversation-a") is context

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_two_containers_do_not_share_conversation_contexts() -> None:
    client = httpx.AsyncClient()
    first = await create_application_container(settings(), http_client=client)
    second = await create_application_container(settings(), http_client=client)

    first_context = await first.conversation_context_store.get_or_create(
        "conversation-a"
    )
    first_context.set_booking_date(date(2026, 8, 2))
    await first.conversation_context_store.save("conversation-a", first_context)
    second_context = await second.conversation_context_store.get_or_create(
        "conversation-a"
    )

    assert second_context is not first_context
    assert second_context.booking_date is None

    await first.close()
    await second.close()
    await client.aclose()
