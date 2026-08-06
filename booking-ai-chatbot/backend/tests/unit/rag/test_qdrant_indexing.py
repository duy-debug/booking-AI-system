"""Tests for explicit offline Qdrant knowledge indexing."""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from qdrant_client import models
from qdrant_client.http.models import CollectionInfo

from app.infrastructure.qdrant_client import (
    EmptyKnowledgeDocumentError,
    IncompatibleCollectionError,
    InvalidIndexingSourceError,
    KnowledgeIndexingError,
    QdrantIndexClient,
    _settings_from_environment,
    index_knowledge_document,
    point_id_for_chunk,
)


class FakeEmbedding:
    def __init__(self, *, dimension: int = 3, vector_count_offset: int = 0) -> None:
        self.dimension = dimension
        self.vector_count_offset = vector_count_offset
        self.calls: list[tuple[str, ...]] = []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        supplied = tuple(texts)
        self.calls.append(supplied)
        count = len(supplied) + self.vector_count_offset
        return [[float(index)] * self.dimension for index in range(max(0, count))]


class FakeQdrantClient:
    def __init__(
        self,
        *,
        existing: bool = False,
        size: int = 3,
        distance: models.Distance = models.Distance.COSINE,
    ) -> None:
        self.exists = existing
        self.size = size
        self.distance = distance
        self.created: list[models.VectorParams] = []
        self.collection_deletions = 0
        self.source_deletions: list[str] = []
        self.points: dict[str, models.PointStruct] = {}

    def collection_exists(self, collection_name: str) -> bool:
        return self.exists

    def get_collection(self, collection_name: str) -> CollectionInfo:
        information = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=models.VectorParams(size=self.size, distance=self.distance)
                )
            )
        )
        return cast(CollectionInfo, information)

    def create_collection(
        self,
        collection_name: str,
        vectors_config: models.VectorParams,
    ) -> bool:
        self.exists = True
        self.size = vectors_config.size
        self.distance = vectors_config.distance
        self.created.append(vectors_config)
        return True

    def delete_collection(self, collection_name: str) -> bool:
        self.exists = False
        self.points.clear()
        self.collection_deletions += 1
        return True

    def delete(
        self,
        collection_name: str,
        points_selector: models.FilterSelector,
        *,
        wait: bool,
    ) -> object:
        conditions = points_selector.filter.must
        assert isinstance(conditions, list)
        condition = cast(models.FieldCondition, conditions[0])
        source = cast(models.MatchValue, condition.match).value
        assert isinstance(source, str)
        self.source_deletions.append(source)
        self.points = {
            point_id: point
            for point_id, point in self.points.items()
            if point.payload is None or point.payload.get("source") != source
        }
        return object()

    def upsert(
        self,
        collection_name: str,
        points: Sequence[models.PointStruct],
        *,
        wait: bool,
    ) -> object:
        for point in points:
            self.points[str(point.id)] = point
        return object()


def source_file(tmp_path: Path, content: str = "# FAQ\n\nFirst answer.\n\nSecond answer.") -> Path:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    source = knowledge / "README.md"
    source.write_text(content, encoding="utf-8")
    return source


def index(
    source: Path,
    *,
    embedding: FakeEmbedding | None = None,
    client: FakeQdrantClient | None = None,
    recreate: bool = False,
) -> tuple[FakeEmbedding, FakeQdrantClient]:
    configured_embedding = embedding or FakeEmbedding()
    configured_client = client or FakeQdrantClient()
    index_knowledge_document(
        source=source,
        embedding=configured_embedding,
        client=cast(QdrantIndexClient, configured_client),
        collection_name="kb_chunks",
        recreate=recreate,
    )
    return configured_embedding, configured_client


def test_import_does_not_construct_qdrant_client_or_affect_app_startup() -> None:
    code = (
        "import sys; import app.main; "
        "assert 'app.infrastructure.qdrant_client' in sys.modules; "
        "assert not hasattr(app.main, 'qdrant_client')"
    )

    result = subprocess.run([sys.executable, "-c", code], check=False)

    assert result.returncode == 0


def test_missing_source_is_rejected_without_embedding(tmp_path: Path) -> None:
    embedding = FakeEmbedding()

    with pytest.raises(InvalidIndexingSourceError):
        index(tmp_path / "missing.md", embedding=embedding)

    assert embedding.calls == []


def test_empty_chunk_result_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(EmptyKnowledgeDocumentError):
        index(source_file(tmp_path, "# Heading only\n"))


def test_embedding_is_one_batch_and_collection_is_created(tmp_path: Path) -> None:
    embedding, client = index(source_file(tmp_path))

    assert len(embedding.calls) == 1
    assert len(embedding.calls[0]) == 1
    assert len(client.created) == 1
    assert client.created[0].size == embedding.dimension
    assert client.created[0].distance is models.Distance.COSINE
    assert len(client.points) == 1


def test_vector_count_must_match_chunks(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeIndexingError, match="count"):
        index(
            source_file(tmp_path),
            embedding=FakeEmbedding(vector_count_offset=-1),
        )


def test_compatible_collection_is_reused(tmp_path: Path) -> None:
    client = FakeQdrantClient(existing=True)

    index(source_file(tmp_path), client=client)

    assert client.created == []
    assert client.collection_deletions == 0


@pytest.mark.parametrize(
    "client",
    [
        FakeQdrantClient(existing=True, size=4),
        FakeQdrantClient(existing=True, distance=models.Distance.DOT),
    ],
)
def test_incompatible_collection_fails_without_recreate(
    tmp_path: Path,
    client: FakeQdrantClient,
) -> None:
    with pytest.raises(IncompatibleCollectionError):
        index(source_file(tmp_path), client=client)

    assert client.collection_deletions == 0
    assert client.created == []


def test_explicit_recreate_deletes_and_creates_collection(tmp_path: Path) -> None:
    client = FakeQdrantClient(existing=True, size=99)

    index(source_file(tmp_path), client=client, recreate=True)

    assert client.collection_deletions == 1
    assert len(client.created) == 1
    assert client.created[0].size == 3


def test_point_identity_is_deterministic_and_chunk_specific() -> None:
    assert point_id_for_chunk("kc_one") == point_id_for_chunk("kc_one")
    assert point_id_for_chunk("kc_one") != point_id_for_chunk("kc_two")


def test_payload_is_minimal_logical_and_contains_no_vector(tmp_path: Path) -> None:
    _, client = index(source_file(tmp_path))
    point = next(iter(client.points.values()))

    assert set(point.payload or {}) == {"chunk_id", "content", "source", "section", "chunk_index"}
    assert point.payload is not None
    assert point.payload["source"] == "knowledge/README.md"
    assert not Path(cast(str, point.payload["source"])).is_absolute()
    assert "vector" not in point.payload
    assert "api_key" not in point.payload


def test_rerun_source_replaces_points_without_duplicates(tmp_path: Path) -> None:
    source = source_file(tmp_path)
    client = FakeQdrantClient()

    index(source, client=client)
    first_ids = set(client.points)
    index(source, client=client)

    assert set(client.points) == first_ids
    assert client.source_deletions == ["knowledge/README.md", "knowledge/README.md"]


def test_source_replace_removes_stale_points(tmp_path: Path) -> None:
    source = source_file(tmp_path)
    client = FakeQdrantClient()
    index(source, client=client)
    client.points["stale"] = models.PointStruct(
        id="11111111-1111-1111-1111-111111111111",
        vector=[0.0, 0.0, 0.0],
        payload={"source": "knowledge/README.md"},
    )

    index(source, client=client)

    assert "stale" not in client.points


def test_blank_collection_name_is_rejected_before_embedding(tmp_path: Path) -> None:
    embedding = FakeEmbedding()

    with pytest.raises(ValueError, match="collection"):
        index_knowledge_document(
            source=source_file(tmp_path),
            embedding=embedding,
            client=cast(QdrantIndexClient, FakeQdrantClient()),
            collection_name="  ",
        )

    assert embedding.calls == []


def test_empty_api_key_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QDRANT_API_KEY", "")

    settings = _settings_from_environment()

    assert settings.qdrant_api_key is None


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("QDRANT_HOST", "https://user:secret@example.test", "hostname"),
        ("QDRANT_PORT", "invalid", "integer"),
        ("QDRANT_PORT", "70000", "between"),
    ],
)
def test_invalid_qdrant_connection_config_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        _settings_from_environment()
