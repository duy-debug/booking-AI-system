"""Unit tests for composition-root settings and resource ownership."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import httpx
import pytest

import app.dependencies as dependencies
from app.application.action_registry import ActionRegistry
from app.dependencies import (
    ConversationContextStore,
    InvalidCachedContextError,
    InvalidConversationContextError,
    InvalidConversationIdError,
)
from app.dialog.flow_loader import FlowDefinition, FlowLoader, FlowTransition
from app.dialog.instruction_builder import InstructionBuilder
from app.domain.booking_context import BookingContext
from app.domain.booking_state import BookingState
from app.infrastructure.context_store import ContextStore, Settings
from app.infrastructure.gemini_client import LLMMessage, LLMResponse
from app.rag_v1 import KnowledgeDocument
from app.rag_v1.retriever import KnowledgeQdrantClient


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


class FakeQdrantClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.query_calls = 0
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_runtime_flow_validation_rejects_unregistered_action() -> None:
    flow = FlowLoader.load(settings().booking_flow_path)

    with pytest.raises(
        dependencies.RuntimeFlowValidationError,
        match="Unregistered flow actions",
    ):
        dependencies.validate_runtime_flow(
            flow,
            ActionRegistry(),
            InstructionBuilder(),
        )


@pytest.mark.asyncio
async def test_runtime_flow_validation_rejects_unsupported_intent() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, request=request))
    )
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
        llm_gateway=FakeLLMGateway(),
    )
    try:
        idle = container.flow_definition.states[BookingState.IDLE]
        invalid_idle = replace(
            idle,
            transitions=idle.transitions
            + (FlowTransition("unsupported_runtime_intent", BookingState.IDLE),),
        )
        invalid_flow = replace(
            container.flow_definition,
            states={**container.flow_definition.states, BookingState.IDLE: invalid_idle},
        )

        with pytest.raises(
            dependencies.RuntimeFlowValidationError,
            match="Unsupported flow intents: unsupported_runtime_intent",
        ):
            dependencies.validate_runtime_flow(
                invalid_flow,
                container.action_registry,
                container.instruction_builder,
            )
    finally:
        await container.close()
        await client.aclose()


class LazyFakeEmbedding:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.embed_calls = 0


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


@pytest.mark.asyncio
async def test_qdrant_feature_disabled_keeps_gateway_none() -> None:
    container = await dependencies.create_application_container(settings())

    assert container.knowledge_gateway is None
    assert container.faq_manager._knowledge_gateway is None
    assert container._qdrant_client is None

    await container.close()


@pytest.mark.asyncio
async def test_disabled_qdrant_does_not_validate_connection_config() -> None:
    configured = Settings(
        pos_base_url="http://pos.test",
        knowledge_qdrant_enabled=False,
        qdrant_host="",
        qdrant_port=0,
        qdrant_collection="",
    )

    container = await dependencies.create_application_container(configured)

    assert container.knowledge_gateway is None
    await container.close()


@pytest.mark.asyncio
async def test_qdrant_feature_enabled_injects_lazy_gateway_without_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients: list[FakeQdrantClient] = []
    embeddings: list[LazyFakeEmbedding] = []

    def client_factory(**kwargs: object) -> FakeQdrantClient:
        client = FakeQdrantClient(**kwargs)
        clients.append(client)
        return client

    def embedding_factory(model_name: str) -> LazyFakeEmbedding:
        embedding = LazyFakeEmbedding(model_name)
        embeddings.append(embedding)
        return embedding

    monkeypatch.setattr(dependencies, "QdrantClient", client_factory)
    monkeypatch.setattr(
        dependencies,
        "EmbeddingModel",
        embedding_factory,
    )
    configured = Settings(
        pos_base_url="http://pos.test",
        knowledge_qdrant_enabled=True,
        qdrant_host="qdrant.test",
        qdrant_port=6333,
        qdrant_api_key="private-key",
        qdrant_collection="knowledge",
        embedding_model_name="configured-model",
    )

    container = await dependencies.create_application_container(configured)

    assert isinstance(container.knowledge_gateway, KnowledgeQdrantClient)
    assert container.faq_manager._knowledge_gateway is container.knowledge_gateway
    assert clients[0].kwargs == {
        "host": "qdrant.test",
        "port": 6333,
        "api_key": "private-key",
    }
    assert clients[0].query_calls == 0
    assert embeddings[0].model_name == "configured-model"
    assert embeddings[0].embed_calls == 0

    await container.close()
    assert clients[0].closed


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"qdrant_host": ""}, "host"),
        ({"qdrant_host": "https://user:secret@qdrant.test"}, "host"),
        ({"qdrant_port": 0}, "port"),
        ({"qdrant_collection": "  "}, "collection"),
    ],
)
@pytest.mark.asyncio
async def test_enabled_qdrant_rejects_invalid_config(
    overrides: dict[str, object],
    message: str,
) -> None:
    configured = Settings(
        pos_base_url="http://pos.test",
        knowledge_qdrant_enabled=True,
        qdrant_host=cast(str, overrides.get("qdrant_host", "localhost")),
        qdrant_port=cast(int, overrides.get("qdrant_port", 6333)),
        qdrant_collection=cast(
            str,
            overrides.get("qdrant_collection", "kb_chunks"),
        ),
    )

    with pytest.raises(ValueError, match=message):
        await dependencies.create_application_container(configured)


@pytest.mark.asyncio
async def test_qdrant_config_is_forwarded_to_dense_rag_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients: list[FakeQdrantClient] = []
    captured_gateway_kwargs: dict[str, object] = {}

    class FakeKnowledgeGateway:
        def __init__(self, **kwargs: object) -> None:
            captured_gateway_kwargs.update(kwargs)

    def client_factory(**kwargs: object) -> FakeQdrantClient:
        client = FakeQdrantClient(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(dependencies, "QdrantClient", client_factory)
    monkeypatch.setattr(
        dependencies,
        "EmbeddingModel",
        lambda model_name: LazyFakeEmbedding(model_name),
    )
    monkeypatch.setattr(dependencies, "KnowledgeQdrantClient", FakeKnowledgeGateway)

    configured = Settings(
        pos_base_url="http://pos.test",
        knowledge_qdrant_enabled=True,
        qdrant_host="qdrant.test",
        qdrant_port=6333,
        qdrant_collection="knowledge",
        embedding_model_name="configured-model",
    )

    container = await dependencies.create_application_container(configured)

    assert isinstance(container.knowledge_gateway, FakeKnowledgeGateway)
    assert captured_gateway_kwargs["collection_name"] == "knowledge"
    assert set(captured_gateway_kwargs) == {"client", "embedding", "collection_name"}

    await container.close()
    assert clients[0].closed


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
            float, overrides.get("pos_timeout_seconds", defaults.pos_timeout_seconds)
        ),
        booking_flow_path=cast(
            Path,
            overrides.get("booking_flow_path", defaults.booking_flow_path),
        ),
        max_auto_transitions=cast(
            int, overrides.get("max_auto_transitions", defaults.max_auto_transitions)
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
        await dependencies.create_application_container(settings(booking_flow_path=invalid_flow))

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

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_factory_injects_one_llm_gateway_into_nlu() -> None:
    client = httpx.AsyncClient()
    gateway = FakeLLMGateway()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
        llm_gateway=gateway,
    )

    assert container.llm_gateway is gateway
    assert container.llm_nlu._llm_gateway is gateway

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

    assert container.faq_manager._knowledge_gateway is gateway
    assert container.faq_manager._instruction_builder is container.instruction_builder

    await container.close()
    await client.aclose()


@pytest.mark.asyncio
async def test_factory_allows_missing_knowledge_gateway() -> None:
    client = httpx.AsyncClient()
    container = await dependencies.create_application_container(
        settings(),
        http_client=client,
    )

    assert container.faq_manager._knowledge_gateway is None

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
    store = ConversationContextStore(cache=ContextStore())

    with pytest.raises(InvalidConversationIdError):
        await store.get_copy(conversation_id)


@pytest.mark.asyncio
async def test_context_store_normalizes_and_reuses_a_valid_conversation_id() -> None:
    cache = ContextStore()
    store = ConversationContextStore(cache=cache)

    created = await store.get_copy("  conversation-1  ")
    loaded = await store.get_copy("conversation-1")

    assert created.conversation_id == "conversation-1"
    assert loaded == created
    assert loaded is not created
    assert await cache.get("conversation-1") == created


@pytest.mark.asyncio
async def test_context_store_keeps_conversations_independent() -> None:
    store = ConversationContextStore(cache=ContextStore())

    first = await store.get_copy("conversation-1")
    second = await store.get_copy("conversation-2")

    assert first is not second
    assert first.conversation_id != second.conversation_id


@pytest.mark.asyncio
async def test_conversation_lock_serializes_same_session_and_cleans_up() -> None:
    store = ConversationContextStore(cache=ContextStore())
    active = 0
    maximum_active = 0

    async def worker() -> None:
        nonlocal active, maximum_active
        async with store.conversation_lock("conversation-1"):
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0)
            active -= 1

    await asyncio.gather(worker(), worker())

    assert maximum_active == 1
    assert store._conversation_locks == {}


@pytest.mark.asyncio
async def test_conversation_lock_allows_different_sessions_in_parallel() -> None:
    store = ConversationContextStore(cache=ContextStore())
    both_entered = asyncio.Event()
    release = asyncio.Event()
    active = 0

    async def worker(conversation_id: str) -> None:
        nonlocal active
        async with store.conversation_lock(conversation_id):
            active += 1
            if active == 2:
                both_entered.set()
            await release.wait()
            active -= 1

    tasks = [
        asyncio.create_task(worker("conversation-1")),
        asyncio.create_task(worker("conversation-2")),
    ]
    await asyncio.wait_for(both_entered.wait(), timeout=1)
    release.set()
    await asyncio.gather(*tasks)

    assert store._conversation_locks == {}


@pytest.mark.asyncio
async def test_context_store_save_preserves_identity_and_state() -> None:
    store = ConversationContextStore(cache=ContextStore())
    context = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
    )

    await store.save("conversation-1", context)
    loaded = await store.get_copy("conversation-1")

    assert loaded == context
    assert loaded is not context
    assert loaded.state is BookingState.SELECTING_SERVICE


@pytest.mark.asyncio
async def test_context_store_save_rejects_non_booking_context() -> None:
    store = ConversationContextStore(cache=ContextStore())

    with pytest.raises(InvalidConversationContextError):
        await store.save("conversation-1", cast(BookingContext, object()))


@pytest.mark.asyncio
async def test_context_store_save_rejects_mismatched_identity() -> None:
    store = ConversationContextStore(cache=ContextStore())
    context = BookingContext(conversation_id="conversation-2")

    with pytest.raises(InvalidConversationContextError):
        await store.save("conversation-1", context)


@pytest.mark.asyncio
async def test_context_store_rejects_invalid_cached_value() -> None:
    cache = ContextStore()
    cache._contexts["conversation-1"] = cast(BookingContext, object())
    store = ConversationContextStore(cache=cache)

    with pytest.raises(InvalidCachedContextError):
        await store.get_copy("conversation-1")


@pytest.mark.asyncio
async def test_context_store_reset_replaces_context_and_preserves_other_conversation() -> None:
    cache = ContextStore()
    store = ConversationContextStore(cache=cache)
    original = BookingContext(
        conversation_id="conversation-1",
        state=BookingState.SELECTING_SERVICE,
        phone="0901234567",
        last_failure_code="search_courses",
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
    assert reset_context.last_failure_code is None
    assert await cache.get("conversation-1") == reset_context
    assert await cache.get("conversation-2") == other
