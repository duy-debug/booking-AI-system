"""Tests for the in-process booking context cache."""

import pytest

from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.cache.memory_cache import MemoryCache


def test_new_cache_is_empty() -> None:
    cache = MemoryCache()

    assert len(cache) == 0


@pytest.mark.asyncio
async def test_get_returns_none_for_missing_conversation() -> None:
    cache = MemoryCache()

    assert await cache.get("missing") is None
    assert len(cache) == 0


@pytest.mark.asyncio
async def test_save_and_get_preserve_object_identity() -> None:
    cache = MemoryCache()
    context = BookingContext(conversation_id="conversation-1")

    await cache.save(context)
    loaded_context = await cache.get("conversation-1")

    assert loaded_context is context
    assert len(cache) == 1


@pytest.mark.asyncio
async def test_save_replaces_context_with_same_conversation_id() -> None:
    cache = MemoryCache()
    original_context = BookingContext(conversation_id="conversation-1")
    replacement_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SHOP,
    )

    await cache.save(original_context)
    await cache.save(replacement_context)

    assert await cache.get("conversation-1") is replacement_context
    assert len(cache) == 1


@pytest.mark.asyncio
async def test_different_conversations_store_independent_contexts() -> None:
    cache = MemoryCache()
    first_context = BookingContext(conversation_id="conversation-1")
    second_context = BookingContext(conversation_id="conversation-2")

    await cache.save(first_context)
    await cache.save(second_context)

    assert await cache.get("conversation-1") is first_context
    assert await cache.get("conversation-2") is second_context
    assert len(cache) == 2


@pytest.mark.asyncio
async def test_delete_removes_existing_context() -> None:
    cache = MemoryCache()
    context = BookingContext(conversation_id="conversation-1")
    await cache.save(context)

    await cache.delete("conversation-1")

    assert await cache.get("conversation-1") is None
    assert len(cache) == 0


@pytest.mark.asyncio
async def test_delete_missing_context_does_not_raise() -> None:
    cache = MemoryCache()

    await cache.delete("missing")

    assert len(cache) == 0


@pytest.mark.asyncio
async def test_get_or_create_creates_and_stores_idle_context() -> None:
    cache = MemoryCache()

    context = await cache.get_or_create("conversation-1")

    assert context.conversation_id == "conversation-1"
    assert context.state is BookingState.IDLE
    assert await cache.get("conversation-1") is context
    assert len(cache) == 1


@pytest.mark.asyncio
async def test_get_or_create_returns_existing_context_without_resetting_it() -> None:
    cache = MemoryCache()
    existing_context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
        pending_action="search_services",
    )
    await cache.save(existing_context)

    returned_context = await cache.get_or_create("conversation-1")

    assert returned_context is existing_context
    assert returned_context.state is BookingState.SELECTING_SERVICE
    assert returned_context.pending_action == "search_services"
    assert len(cache) == 1


@pytest.mark.asyncio
async def test_mutation_is_visible_on_subsequent_get() -> None:
    cache = MemoryCache()
    context = await cache.get_or_create("conversation-1")

    context.state = BookingState.SELECTING_SHOP
    loaded_context = await cache.get("conversation-1")

    assert loaded_context is context
    assert loaded_context.state is BookingState.SELECTING_SHOP
