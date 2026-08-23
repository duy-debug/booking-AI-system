"""Tests for semantic Qdrant vector-store retrieval."""

from typing import cast

import pytest
from qdrant_client import models
from qdrant_client.http.models.models import QueryResponse

from app.rag_v1.vector_store import SearchResult, VectorStore


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
    ) -> QueryResponse:
        self.calls.append(
            {
                "collection_name": collection_name,
                "query": query,
                "limit": limit,
                "with_payload": with_payload,
            }
        )
        if self.error is not None:
            raise self.error
        return QueryResponse(points=self.points)


def point(
    point_id: int,
    *,
    text: object = "Knowledge content",
    source: object = "knowledge/README.md",
    score: float = 0.9,
    vector: list[float] | None = None,
) -> models.ScoredPoint:
    return models.ScoredPoint(
        id=point_id,
        version=1,
        score=score,
        payload={
            "text": text,
            "source": source,
            "file_path": source,
            "chunk_index": point_id,
        },
        vector=vector,
    )


def vector_store(
    client: FakeQueryClient,
) -> VectorStore:
    return VectorStore(
        client=cast(object, client),
        collection_name="kb_chunks",
        vector_size=3,
    )


def test_constructor_does_not_query() -> None:
    client = FakeQueryClient()

    vector_store(client)

    assert client.calls == []


@pytest.mark.parametrize("query_vector", [[], [0.1], [0.1, 0.2]])
def test_invalid_query_vector_dimension_is_rejected(
    query_vector: list[float],
) -> None:
    store = vector_store(FakeQueryClient())

    with pytest.raises(ValueError, match="vector size"):
        store.search(query_vector)


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_limit_is_rejected(limit: int) -> None:
    store = vector_store(FakeQueryClient())

    with pytest.raises(ValueError, match="limit"):
        store.search([0.1, 0.2, 0.3], limit=limit)


def test_query_uses_collection_limit_and_payload_policy() -> None:
    client = FakeQueryClient([point(1)])
    store = vector_store(client)

    results = store.search([0.1, 0.2, 0.3], limit=3)

    assert client.calls == [
        {
            "collection_name": "kb_chunks",
            "query": [0.1, 0.2, 0.3],
            "limit": 3,
            "with_payload": True,
        }
    ]
    assert results == [
        SearchResult(
            text="Knowledge content",
            source="knowledge/README.md",
            file_path="knowledge/README.md",
            chunk_index=1,
            score=0.9,
        )
    ]


def test_empty_result_returns_empty_list() -> None:
    store = vector_store(FakeQueryClient())

    assert store.search([0.1, 0.2, 0.3]) == []


def test_ranking_is_preserved() -> None:
    client = FakeQueryClient(
        [
            point(9, text="First", score=0.95, vector=[9.0]),
            point(2, text="Second", score=0.80, vector=[2.0]),
        ]
    )
    store = vector_store(client)

    results = store.search([0.1, 0.2, 0.3])

    assert [result.text for result in results] == ["First", "Second"]


def test_infrastructure_error_is_not_hidden() -> None:
    store = vector_store(FakeQueryClient(error=OSError("offline")))

    with pytest.raises(OSError, match="offline"):
        store.search([0.1, 0.2, 0.3])
