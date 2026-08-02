"""Unit tests for composition-root settings and resource ownership."""

import json
from pathlib import Path
from typing import cast

import httpx
import pytest

import app.dependencies as dependencies
from app.application.ports.knowledge_gateway import KnowledgeDocument
from app.application.ports.llm_gateway import LLMMessage, LLMResponse
from app.core.config import Settings
from app.dependencies import (
    ConversationContextStore,
    InvalidCachedContextError,
    InvalidConversationContextError,
    InvalidConversationIdError,
)
from app.dialog.flow_loader import FlowDefinition, FlowLoader
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.cache.memory_cache import MemoryCache


class FakeLLMGateway:
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="{}")


class FakeKnowledgeGateway:
    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeDocument]:
        return []


def settings(
    *,
    pos_base_url: str = "http://pos.test",
    pos_timeout_seconds: float = 10.0,
    booking_flow_path: Path | None = None,
    max_auto_transitions: int = 8,
) -> Settings:
    if booking_flow_path is None:
        return Settings(
            pos_base_url=pos_base_url,
            pos_timeout_seconds=pos_timeout_seconds,
            max_auto_transitions=max_auto_transitions,
        )
    return Settings(
        pos_base_url=pos_base_url,
        pos_timeout_seconds=pos_timeout_seconds,
        booking_flow_path=booking_flow_path,
        max_auto_transitions=max_auto_transitions,
    )


@pytest.mark.asyncio
async def test_owned_client_is_closed_idempotently() -> None:
    container = await dependencies.create_application_container(settings())

    assert not container.http_client.is_closed

    await container.close()
    await container.close()

    assert container.http_client.is_closed


@pytest.mark.asyncio
async def test_injected_client_is_not_closed() -> None:
    def unused_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(unused_transport))
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
    )

    await container.close()

    assert not client.is_closed
    await client.aclose()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"pos_base_url": "  "}, "base URL"),
        ({"pos_timeout_seconds": 0}, "timeout"),
        ({"pos_timeout_seconds": -1}, "timeout"),
        ({"max_auto_transitions": 0}, "auto transitions"),
        ({"booking_flow_path": Path("missing-flow.json")}, "flow path"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_settings_are_rejected_before_container_creation(
    overrides: dict[str, object],
    message: str,
) -> None:
    defaults = settings()
    invalid = Settings(
        pos_base_url=str(overrides.get("pos_base_url", defaults.pos_base_url)),
        pos_timeout_seconds=cast(
            float,
            overrides.get("pos_timeout_seconds", defaults.pos_timeout_seconds)
        ),
        booking_flow_path=cast(
            Path,
            overrides.get("booking_flow_path", defaults.booking_flow_path),
        ),
        max_auto_transitions=cast(
            int,
            overrides.get("max_auto_transitions", defaults.max_auto_transitions)
        ),
    )
    with pytest.raises(ValueError, match=message):
        await dependencies.create_application_container(invalid)


@pytest.mark.asyncio
async def test_owned_client_is_closed_when_flow_loading_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_flow = tmp_path / "invalid.json"
    invalid_flow.write_text("{", encoding="utf-8")
    client = httpx.AsyncClient()
    monkeypatch.setattr(dependencies.httpx, "AsyncClient", lambda **kwargs: client)

    with pytest.raises(json.JSONDecodeError):
        await dependencies.create_application_container(
            settings(booking_flow_path=invalid_flow)
        )

    assert client.is_closed


@pytest.mark.asyncio
async def test_injected_client_is_not_closed_when_flow_loading_fails(
    tmp_path: Path,
) -> None:
    invalid_flow = tmp_path / "invalid.json"
    invalid_flow.write_text("{", encoding="utf-8")
    client = httpx.AsyncClient()

    with pytest.raises(json.JSONDecodeError):
        await dependencies.create_application_container(
            settings(booking_flow_path=invalid_flow),
            http_client=client,
        )

    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_factory_loads_flow_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path] = []
    original_load = FlowLoader.load

    def load_spy(path: Path) -> FlowDefinition:
        calls.append(path)
        return original_load(path)

    monkeypatch.setattr(FlowLoader, "load", staticmethod(load_spy))
    client = httpx.AsyncClient()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
    )

    assert calls == [settings().booking_flow_path]

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_lifespan_closes_owned_container() -> None:
    async with dependencies.application_container_lifespan(settings()) as container:
        client = container.http_client
        assert not client.is_closed

    assert client.is_closed


@pytest.mark.asyncio
async def test_dependency_getters_return_container_instances() -> None:
    client = httpx.AsyncClient()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
    )

    assert dependencies.get_dialog_controller(container) is container.dialog_controller
    assert dependencies.get_memory_cache(container) is container.memory_cache

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_factory_injects_one_llm_gateway_into_the_fallback() -> None:
    client = httpx.AsyncClient()
    gateway = FakeLLMGateway()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
        llm_gateway=gateway,
    )

    assert container.llm_gateway is gateway
    assert container.llm_nlu_fallback._llm_gateway is gateway

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_factory_preserves_injected_knowledge_gateway_identity() -> None:
    client = httpx.AsyncClient()
    gateway = FakeKnowledgeGateway()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
        knowledge_gateway=gateway,
    )

    assert container.knowledge_gateway is gateway

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_factory_allows_missing_knowledge_gateway() -> None:
    client = httpx.AsyncClient()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
    )

    assert container.knowledge_gateway is None

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_invalid_llm_confidence_setting_is_rejected() -> None:
    invalid = Settings(
        pos_base_url="http://pos.test",
        llm_nlu_min_confidence=1.1,
    )

    with pytest.raises(ValueError, match="confidence"):
        await dependencies.create_application_container(invalid)


@pytest.mark.parametrize(
    "conversation_id",
    ["", "   ", "x" * 129, "0901234567", "+84 901-234-567"],
)
@pytest.mark.asyncio
async def test_context_store_rejects_invalid_conversation_ids(
    conversation_id: str,
) -> None:
    store = ConversationContextStore(cache=MemoryCache())

    with pytest.raises(InvalidConversationIdError):
        await store.get_or_create(conversation_id)


@pytest.mark.asyncio
async def test_context_store_normalizes_and_reuses_a_valid_conversation_id() -> None:
    cache = MemoryCache()
    store = ConversationContextStore(cache=cache)

    created = await store.get_or_create("  conversation-1  ")
    loaded = await store.get_or_create("conversation-1")

    assert created.conversation_id == "conversation-1"
    assert loaded is created
    assert await cache.get("conversation-1") is created


@pytest.mark.asyncio
async def test_context_store_keeps_conversations_independent() -> None:
    store = ConversationContextStore(cache=MemoryCache())

    first = await store.get_or_create("conversation-1")
    second = await store.get_or_create("conversation-2")

    assert first is not second
    assert first.conversation_id != second.conversation_id


@pytest.mark.asyncio
async def test_context_store_save_preserves_identity_and_state() -> None:
    store = ConversationContextStore(cache=MemoryCache())
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
    )

    await store.save("conversation-1", context)
    loaded = await store.get_or_create("conversation-1")

    assert loaded is context
    assert loaded.state is BookingState.SELECTING_SERVICE


@pytest.mark.asyncio
async def test_context_store_save_rejects_non_booking_context() -> None:
    store = ConversationContextStore(cache=MemoryCache())

    with pytest.raises(InvalidConversationContextError):
        await store.save("conversation-1", cast(BookingContext, object()))


@pytest.mark.asyncio
async def test_context_store_save_rejects_mismatched_identity() -> None:
    store = ConversationContextStore(cache=MemoryCache())
    context = BookingContext(conversation_id="conversation-2")

    with pytest.raises(InvalidConversationContextError):
        await store.save("conversation-1", context)


@pytest.mark.asyncio
async def test_context_store_rejects_invalid_cached_value() -> None:
    cache = MemoryCache()
    cache._contexts["conversation-1"] = cast(BookingContext, object())
    store = ConversationContextStore(cache=cache)

    with pytest.raises(InvalidCachedContextError):
        await store.get_or_create("conversation-1")


@pytest.mark.asyncio
async def test_context_store_reset_replaces_context_and_preserves_other_conversation() -> None:
    cache = MemoryCache()
    store = ConversationContextStore(cache=cache)
    original = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
        phone="0901234567",
        pending_action="search_services",
    )
    other = BookingContext(
        conversation_id="conversation-2",
        state=BookingState.SELECTING_SHOP,
    )
    await cache.save(original)
    await cache.save(other)

    reset_context = await store.reset("conversation-1")

    assert reset_context is not original
    assert reset_context.state is BookingState.IDLE
    assert reset_context.phone is None
    assert reset_context.pending_action is None
    assert await cache.get("conversation-1") is reset_context
    assert await cache.get("conversation-2") is other
