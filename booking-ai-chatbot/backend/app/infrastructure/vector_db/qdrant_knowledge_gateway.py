"""Qdrant-backed semantic knowledge retrieval."""

import asyncio
from collections.abc import Sequence
from math import isfinite
from pathlib import PurePosixPath
from typing import Protocol

from qdrant_client import models
from qdrant_client.http.exceptions import ApiException
from qdrant_client.http.models.models import QueryResponse

from app.application.ports.knowledge_gateway import (
    KnowledgeDocument,
    KnowledgeGatewayUnavailableError,
)
from app.rag.semantic_embedding import SentenceTransformerEmbedding


class QdrantQueryClient(Protocol):
    """Narrow Qdrant query boundary required by the knowledge gateway."""

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        *,
        limit: int,
        with_payload: bool,
        with_vectors: bool,
    ) -> QueryResponse: ...


class QdrantKnowledgeGateway:
    """Retrieve ranked knowledge documents using normalized query embeddings."""

    def __init__(
        self,
        *,
        client: QdrantQueryClient,
        embedding: SentenceTransformerEmbedding,
        collection_name: str,
    ) -> None:
        normalized_collection = collection_name.strip()
        if not normalized_collection:
            raise ValueError("Qdrant collection name must not be empty.")
        self._client = client
        self._embedding = embedding
        self._collection_name = normalized_collection

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeDocument]:
        """Return valid Qdrant hits in their original ranking order."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Knowledge query must not be empty.")
        if type(limit) is not int or limit <= 0:
            raise ValueError("Knowledge result limit must be a positive integer.")
        try:
            return await asyncio.to_thread(self._search_sync, query, limit)
        except ApiException as error:
            raise KnowledgeGatewayUnavailableError(
                "Knowledge retrieval infrastructure is unavailable."
            ) from error
        except OSError as error:
            raise KnowledgeGatewayUnavailableError(
                "Knowledge embedding infrastructure is unavailable."
            ) from error

    def _search_sync(self, query: str, limit: int) -> list[KnowledgeDocument]:
        query_vector = self._embedding.embed_query(query)
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return _documents_from_points(response.points)


def _documents_from_points(
    points: Sequence[models.ScoredPoint],
) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for point in points:
        payload = point.payload
        if not isinstance(payload, dict):
            continue
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        source = payload.get("source")
        if source is not None and (
            not isinstance(source, str) or not _is_safe_logical_source(source)
        ):
            continue
        score = point.score
        if isinstance(score, bool) or not isinstance(score, int | float):
            continue
        normalized_score = float(score)
        if not isfinite(normalized_score):
            continue
        documents.append(
            KnowledgeDocument(
                content=content.strip(),
                score=normalized_score,
                source=source,
            )
        )
    return documents


def _is_safe_logical_source(source: str) -> bool:
    path = PurePosixPath(source)
    return bool(
        source
        and not path.is_absolute()
        and "\\" not in source
        and all(part not in {"", ".", ".."} for part in path.parts)
    )
