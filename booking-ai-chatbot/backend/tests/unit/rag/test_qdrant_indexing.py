"""Tests for flat rag_v1 indexing orchestration."""

from pathlib import Path

import pytest

from app.rag_v1.chunker import Chunk, DocumentChunker
from app.rag_v1.config import RAGConfig
from app.rag_v1.indexer import KnowledgeIndexer
from app.rag_v1.loader import DocumentLoader
from app.rag_v1.vector_store import VectorStore, point_id_for_chunk


class FakeEmbedding:
    def __init__(self) -> None:
        self.calls: list[list[Chunk]] = []

    def embed_chunks(self, chunks: list[Chunk]) -> list[list[float]]:
        self.calls.append(chunks)
        return [[float(index), 0.0, 1.0] for index, _ in enumerate(chunks)]


class FakeVectorStore:
    def __init__(self) -> None:
        self.created = False
        self.recreated = False
        self.deleted_sources: list[str] = []
        self.upserts: list[tuple[list[Chunk], list[list[float]]]] = []

    def create_collection(self) -> None:
        self.created = True

    def recreate_collection(self) -> None:
        self.recreated = True

    def delete_sources(self, sources: list[str]) -> None:
        self.deleted_sources = sources

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        self.upserts.append((chunks, vectors))


class FakeQdrantClient:
    def __init__(self) -> None:
        self.collection_created = False
        self.points: list[object] = []

    def collection_exists(self, collection_name: str) -> bool:
        return self.collection_created

    def create_collection(self, **kwargs: object) -> None:
        self.collection_created = True

    def upsert(self, *, collection_name: str, points: list[object]) -> None:
        self.points.extend(points)


def test_indexer_runs_loader_chunker_embedding_and_vector_store(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "faq.md").write_text("abcdef", encoding="utf-8")
    embedding = FakeEmbedding()
    vector_store = FakeVectorStore()
    indexer = KnowledgeIndexer(
        loader=DocumentLoader(),
        chunker=DocumentChunker(chunk_size=3, chunk_overlap=0),
        embedder=embedding,  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
    )

    indexed_count = indexer.index_directory(root)

    assert indexed_count == 2
    assert vector_store.created
    assert vector_store.deleted_sources == ["faq.md"]
    assert [chunk.text for chunk in embedding.calls[0]] == ["abc", "def"]
    assert vector_store.upserts[0][1] == [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]]


def test_indexer_can_recreate_collection_instead_of_deleting_sources(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "faq.md").write_text("abcdef", encoding="utf-8")
    vector_store = FakeVectorStore()
    indexer = KnowledgeIndexer(
        loader=DocumentLoader(),
        chunker=DocumentChunker(chunk_size=3, chunk_overlap=0),
        embedder=FakeEmbedding(),  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
        config=RAGConfig(recreate_collection_on_index=True),
    )

    assert indexer.index_directory(root) == 2
    assert vector_store.recreated
    assert vector_store.deleted_sources == []


def test_indexer_returns_zero_when_folder_has_no_supported_documents(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "ignored.exe").write_text("ignored", encoding="utf-8")
    vector_store = FakeVectorStore()
    indexer = KnowledgeIndexer(
        loader=DocumentLoader(),
        chunker=DocumentChunker(),
        embedder=FakeEmbedding(),  # type: ignore[arg-type]
        vector_store=vector_store,  # type: ignore[arg-type]
    )

    assert indexer.index_directory(root) == 0
    assert not vector_store.created
    assert vector_store.upserts == []


def test_vector_store_creates_collection_and_upserts_payload() -> None:
    client = FakeQdrantClient()
    store = VectorStore(
        collection_name="knowledge",
        vector_size=3,
        client=client,  # type: ignore[arg-type]
    )
    chunk = Chunk("content", "faq.md", "knowledge/faq.md", 0)

    store.create_collection()
    store.upsert([chunk], [[0.1, 0.2, 0.3]])

    assert client.collection_created
    assert len(client.points) == 1
    point = client.points[0]
    assert point.payload == {
        "text": "content",
        "source": "faq.md",
        "file_path": "knowledge/faq.md",
        "chunk_index": 0,
    }


def test_vector_store_rejects_invalid_vector_size() -> None:
    store = VectorStore(
        collection_name="knowledge",
        vector_size=3,
        client=FakeQdrantClient(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="vector size"):
        store.upsert([Chunk("content", "faq.md", "faq.md", 0)], [[0.1, 0.2]])


def test_point_id_for_chunk_is_deterministic() -> None:
    chunk = Chunk("content", "faq.md", "knowledge/faq.md", 0)

    assert point_id_for_chunk(chunk) == point_id_for_chunk(chunk)


def test_rag_config_rejects_invalid_reindex_settings() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        RAGConfig(chunk_size=100, chunk_overlap=100)
