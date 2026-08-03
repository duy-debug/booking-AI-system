"""Manually index one Markdown knowledge document into Qdrant."""

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID, uuid5

from qdrant_client import QdrantClient, models
from qdrant_client.http.models import CollectionInfo

from app.core.config import Settings
from app.rag.markdown_ingestion import (
    KnowledgeChunk,
    MarkdownKnowledgeLoader,
    SectionAwareMarkdownChunker,
)
from app.rag.semantic_embedding import SentenceTransformerEmbedding

_POINT_ID_NAMESPACE = UUID("f3050e37-e832-5c11-9a82-8d86e2251dc9")


class KnowledgeIndexingError(Exception):
    """Base error for expected knowledge-indexing failures."""


class InvalidIndexingSourceError(KnowledgeIndexingError):
    """Raised when the requested source is not an existing Markdown file."""


class EmptyKnowledgeDocumentError(KnowledgeIndexingError):
    """Raised when ingestion produces no indexable chunks."""


class IncompatibleCollectionError(KnowledgeIndexingError):
    """Raised when an existing collection has incompatible vector settings."""


class IndexEmbedding(Protocol):
    """Minimal embedding behavior required by the offline indexer."""

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class QdrantIndexClient(Protocol):
    """Narrow synchronous Qdrant boundary used by the offline indexer."""

    def collection_exists(self, collection_name: str) -> bool: ...

    def get_collection(self, collection_name: str) -> CollectionInfo: ...

    def create_collection(
        self,
        collection_name: str,
        vectors_config: models.VectorParams,
    ) -> bool: ...

    def delete_collection(self, collection_name: str) -> bool: ...

    def delete(
        self,
        collection_name: str,
        points_selector: models.FilterSelector,
        *,
        wait: bool,
    ) -> object: ...

    def upsert(
        self,
        collection_name: str,
        points: Sequence[models.PointStruct],
        *,
        wait: bool,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class IndexingSummary:
    """Non-sensitive result returned by one indexing run."""

    collection_name: str
    source: str
    chunk_count: int
    vector_dimension: int


def index_knowledge_document(
    *,
    source: Path,
    embedding: IndexEmbedding,
    client: QdrantIndexClient,
    collection_name: str,
    recreate: bool = False,
) -> IndexingSummary:
    """Load, embed, source-replace, and upsert one Markdown document."""
    normalized_collection = _validate_collection_name(collection_name)
    source_path = source.resolve()
    if not source_path.is_file():
        raise InvalidIndexingSourceError(
            "Knowledge source must be an existing regular file."
        )
    loader = MarkdownKnowledgeLoader(source_path.parent)
    document = loader.load(Path(source_path.name))
    chunks = SectionAwareMarkdownChunker().chunk(document)
    if not chunks:
        raise EmptyKnowledgeDocumentError(
            "Knowledge source produced no indexable chunks."
        )

    vectors = embedding.embed_documents([chunk.content for chunk in chunks])
    if len(vectors) != len(chunks):
        raise KnowledgeIndexingError(
            "Embedding output count does not match the knowledge chunk count."
        )
    vector_dimension = embedding.dimension
    if any(len(vector) != vector_dimension for vector in vectors):
        raise KnowledgeIndexingError(
            "Embedding output contains an inconsistent vector dimension."
        )

    _ensure_collection(
        client=client,
        collection_name=normalized_collection,
        vector_dimension=vector_dimension,
        recreate=recreate,
    )
    client.delete(
        collection_name=normalized_collection,
        points_selector=_source_filter(document.source),
        wait=True,
    )
    points = [
        _point_from_chunk(chunk=chunk, vector=vector)
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    client.upsert(
        collection_name=normalized_collection,
        points=points,
        wait=True,
    )
    return IndexingSummary(
        collection_name=normalized_collection,
        source=document.source,
        chunk_count=len(chunks),
        vector_dimension=vector_dimension,
    )


def point_id_for_chunk(chunk_id: str) -> str:
    """Return a stable Qdrant-compatible UUID for one chunk identity."""
    if not chunk_id:
        raise ValueError("Knowledge chunk ID must not be empty.")
    return str(uuid5(_POINT_ID_NAMESPACE, chunk_id))


def _ensure_collection(
    *,
    client: QdrantIndexClient,
    collection_name: str,
    vector_dimension: int,
    recreate: bool,
) -> None:
    exists = client.collection_exists(collection_name)
    if exists and recreate:
        client.delete_collection(collection_name)
        exists = False
    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_dimension,
                distance=models.Distance.COSINE,
            ),
        )
        return
    information = client.get_collection(collection_name)
    vectors_config = information.config.params.vectors
    if not isinstance(vectors_config, models.VectorParams):
        raise IncompatibleCollectionError(
            "Qdrant collection must use one unnamed dense vector."
        )
    if vectors_config.size != vector_dimension:
        raise IncompatibleCollectionError(
            "Qdrant collection vector size does not match the embedding model."
        )
    if vectors_config.distance is not models.Distance.COSINE:
        raise IncompatibleCollectionError(
            "Qdrant collection distance must be cosine."
        )


def _source_filter(source: str) -> models.FilterSelector:
    return models.FilterSelector(
        filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="source",
                    match=models.MatchValue(value=source),
                )
            ]
        )
    )


def _point_from_chunk(
    *,
    chunk: KnowledgeChunk,
    vector: list[float],
) -> models.PointStruct:
    return models.PointStruct(
        id=point_id_for_chunk(chunk.chunk_id),
        vector=vector,
        payload={
            "chunk_id": chunk.chunk_id,
            "content": chunk.content,
            "source": chunk.source,
            "section": chunk.section,
            "chunk_index": chunk.chunk_index,
        },
    )


def _validate_collection_name(collection_name: str) -> str:
    normalized = collection_name.strip()
    if not normalized:
        raise ValueError("Qdrant collection name must not be empty.")
    return normalized


def _settings_from_environment() -> Settings:
    raw_port = os.getenv("QDRANT_PORT", "6333")
    try:
        port = int(raw_port)
    except ValueError as error:
        raise ValueError("Qdrant port must be an integer.") from error
    host = os.getenv("QDRANT_HOST", "localhost").strip()
    if not host:
        raise ValueError("Qdrant host must not be empty.")
    if "://" in host or "/" in host or "@" in host or any(
        character.isspace() for character in host
    ):
        raise ValueError("Qdrant host must be a hostname or IP address.")
    if not 1 <= port <= 65535:
        raise ValueError("Qdrant port must be between 1 and 65535.")
    return Settings(
        pos_base_url=os.getenv("BOOKING_API_URL", "http://localhost:8000"),
        embedding_model_name=os.getenv(
            "EMBED_MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
        qdrant_host=host,
        qdrant_port=port,
        qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "kb_chunks"),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("knowledge/README.md"),
        help="One Markdown knowledge file to index.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Explicitly delete and recreate an existing collection.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit offline indexing command."""
    arguments = _parser().parse_args(argv)
    try:
        settings = _settings_from_environment()
        embedding = SentenceTransformerEmbedding(settings.embedding_model_name)
        client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )
        summary = index_knowledge_document(
            source=arguments.source,
            embedding=embedding,
            client=cast(QdrantIndexClient, client),
            collection_name=settings.qdrant_collection,
            recreate=arguments.recreate,
        )
    except (KnowledgeIndexingError, ValueError) as error:
        print(f"Indexing failed: {error}", file=sys.stderr)
        return 1
    print(
        "Indexed "
        f"collection={summary.collection_name} "
        f"source={summary.source} "
        f"chunks={summary.chunk_count} "
        f"dimension={summary.vector_dimension}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
