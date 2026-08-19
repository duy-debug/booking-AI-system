"""Tests for semantic Qdrant knowledge retrieval."""

import asyncio
import sys
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from qdrant_client import models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.http.models.models import QueryResponse

from app.knowledge import KnowledgeGatewayUnavailableError
from app.knowledge.embeddings.sentence_transformer import SentenceTransformerEmbedding
from app.knowledge.query.retriever import KnowledgeQdrantClient, _LlamaIndexRetrieverFactory
from app.knowledge.stores.qdrant import QdrantQueryClient


class FakeEmbedding:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class FakeQueryClient:
    def __init__(
        self,
        points: list[models.ScoredPoint] | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.points = points or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        *,
        limit: int,
        with_payload: bool,
        with_vectors: bool,
    ) -> QueryResponse:
        self.calls.append(
            {
                "collection_name": collection_name,
                "query": query,
                "limit": limit,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
            }
        )
        if self.error is not None:
            raise self.error
        return QueryResponse(points=self.points)


def point(
    point_id: int,
    *,
    content: object = "Knowledge content",
    source: object = "knowledge/README.md",
    score: float = 0.9,
    vector: list[float] | None = None,
) -> models.ScoredPoint:
    return models.ScoredPoint(
        id=point_id,
        version=1,
        score=score,
        payload={
            "chunk_id": f"kc_{point_id}",
            "content": content,
            "source": source,
            "section": "FAQ",
            "chunk_index": point_id,
        },
        vector=vector,
    )


def gateway(
    client: FakeQueryClient,
    embedding: FakeEmbedding | None = None,
) -> tuple[KnowledgeQdrantClient, FakeEmbedding]:
    configured_embedding = embedding or FakeEmbedding()
    return (
        KnowledgeQdrantClient(
            client=cast(QdrantQueryClient, client),
            embedding=cast(SentenceTransformerEmbedding, configured_embedding),
            collection_name="kb_chunks",
        ),
        configured_embedding,
    )


def test_constructor_does_not_embed_or_query() -> None:
    client = FakeQueryClient()
    _, embedding = gateway(client)

    assert client.calls == []
    assert embedding.queries == []


@pytest.mark.parametrize("query", ["", "  ", "\n\t"])
async def test_empty_query_is_rejected(query: str) -> None:
    knowledge, _ = gateway(FakeQueryClient())

    with pytest.raises(ValueError, match="query"):
        await knowledge.search(query)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
async def test_invalid_limit_is_rejected(limit: object) -> None:
    knowledge, _ = gateway(FakeQueryClient())

    with pytest.raises(ValueError, match="limit"):
        await knowledge.search("query", limit=cast(int, limit))


async def test_query_uses_embedding_collection_limit_and_payload_policy() -> None:
    client = FakeQueryClient([point(1)])
    knowledge, embedding = gateway(client)

    documents = await knowledge.search("original query", limit=3)

    assert embedding.queries == ["original query"]
    assert client.calls == [
        {
            "collection_name": "kb_chunks",
            "query": [0.1, 0.2, 0.3],
            "limit": 3,
            "with_payload": True,
            "with_vectors": False,
        }
    ]
    assert documents[0].content == "Knowledge content"
    assert documents[0].source == "knowledge/README.md"
    assert documents[0].score == 0.9


async def test_empty_result_returns_empty_list() -> None:
    knowledge, _ = gateway(FakeQueryClient())

    assert await knowledge.search("query") == []


async def test_ranking_is_preserved_and_internal_fields_are_not_exposed() -> None:
    client = FakeQueryClient(
        [
            point(9, content="First", score=0.95, vector=[9.0]),
            point(2, content="Second", score=0.80, vector=[2.0]),
        ]
    )
    knowledge, _ = gateway(client)

    documents = await knowledge.search("query")

    assert [document.content for document in documents] == ["First", "Second"]
    assert set(documents[0].__dataclass_fields__) == {"content", "score", "source"}


async def test_invalid_hits_are_skipped_while_valid_hits_are_retained() -> None:
    client = FakeQueryClient(
        [
            point(1, content="  "),
            point(2, content=123),
            point(3, source="C:\\private\\file.md"),
            point(4, content="Valid", source=None),
        ]
    )
    knowledge, _ = gateway(client)

    documents = await knowledge.search("query")

    assert len(documents) == 1
    assert documents[0].content == "Valid"
    assert documents[0].source is None


@pytest.mark.parametrize(
    "error",
    [
        ResponseHandlingException(OSError("offline")),
        UnexpectedResponse(404, "Not Found", b"missing", httpx.Headers()),
        OSError("model missing"),
    ],
)
async def test_infrastructure_failure_maps_to_unavailable(error: Exception) -> None:
    knowledge, _ = gateway(FakeQueryClient(error=error))

    with pytest.raises(KnowledgeGatewayUnavailableError) as exc_info:
        await knowledge.search("query")

    assert exc_info.value.__cause__ is error
    assert "offline" not in str(exc_info.value)


async def test_programmer_error_is_not_hidden() -> None:
    knowledge, _ = gateway(FakeQueryClient(error=TypeError("bug")))

    with pytest.raises(TypeError, match="bug"):
        await knowledge.search("query")


async def test_cancelled_error_propagates() -> None:
    knowledge, _ = gateway(FakeQueryClient(error=asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await knowledge.search("query")


def test_llamaindex_factory_enables_hybrid_query_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    client = cast(QdrantQueryClient, FakeQueryClient())
    embedding = cast(SentenceTransformerEmbedding, FakeEmbedding())

    class FakeIndex:
        def as_retriever(self, **kwargs: object) -> object:
            calls["retriever_kwargs"] = kwargs
            return object()

    class FakeVectorStoreIndex:
        @staticmethod
        def from_vector_store(*, vector_store: object, embed_model: object) -> FakeIndex:
            calls["vector_store"] = vector_store
            calls["embed_model"] = embed_model
            return FakeIndex()

    monkeypatch.setitem(
        sys.modules,
        "llama_index.core",
        SimpleNamespace(VectorStoreIndex=FakeVectorStoreIndex),
    )
    monkeypatch.setattr(
        "app.knowledge.query.retriever.build_qdrant_vector_store",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        "app.knowledge.query.retriever.build_llamaindex_embedding",
        lambda embedding: ("wrapped", embedding),
    )

    factory = _LlamaIndexRetrieverFactory(
        client=client,
        embedding=embedding,
        collection_name="kb_chunks",
        hybrid_enabled=True,
        sparse_top_k=11,
        hybrid_top_k=4,
    )

    factory.build(3)

    assert calls["vector_store"] == {
        "client": client,
        "collection_name": "kb_chunks",
        "enable_hybrid": True,
    }
    assert calls["retriever_kwargs"] == {
        "similarity_top_k": 3,
        "vector_store_query_mode": "hybrid",
        "sparse_top_k": 11,
        "hybrid_top_k": 4,
    }
