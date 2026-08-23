"""Tests for the simple local semantic embedding wrapper."""

import subprocess
import sys
from collections.abc import Sequence

import pytest

import app.rag_v1.embedding as embedding_module
from app.infrastructure.context_store import Settings
from app.rag_v1.chunker import Chunk
from app.rag_v1.embedding import EmbeddingModel


class FakeVectorBatch:
    def __init__(
        self,
        vectors: list[list[float]],
    ) -> None:
        self.vectors = vectors

    def tolist(
        self,
    ) -> list[list[float]]:
        return self.vectors


class FakeVector:
    def __init__(
        self,
        vector: list[float],
    ) -> None:
        self.vector = vector

    def tolist(
        self,
    ) -> list[float]:
        return self.vector


class FakeEncoder:
    def __init__(
        self,
        model_name: str,
    ) -> None:
        self.model_name = model_name
        self.calls: list[tuple[tuple[str, ...] | str, bool]] = []

    def encode(
        self,
        sentences: Sequence[str] | str,
        *,
        normalize_embeddings: bool,
    ) -> FakeVector | FakeVectorBatch:
        self.calls.append(
            (
                tuple(sentences) if not isinstance(sentences, str) else sentences,
                normalize_embeddings,
            )
        )

        if isinstance(sentences, str):
            return FakeVector(
                [
                    0.1,
                    0.2,
                    0.3,
                ]
            )

        return FakeVectorBatch(
            [
                [
                    float(index),
                    0.5,
                    1.0,
                ]
                for index, _ in enumerate(sentences)
            ]
        )


class FakeSentenceTransformersModule:
    def __init__(
        self,
    ) -> None:
        self.encoders: list[FakeEncoder] = []

    def SentenceTransformer(
        self,
        model_name: str,
    ) -> FakeEncoder:
        encoder = FakeEncoder(
            model_name
        )
        self.encoders.append(
            encoder
        )
        return encoder


def patch_sentence_transformers(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeSentenceTransformersModule:
    module = FakeSentenceTransformersModule()
    monkeypatch.setattr(
        embedding_module,
        "import_module",
        lambda name: module,
    )
    return module


def test_model_is_loaded_once_at_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = patch_sentence_transformers(
        monkeypatch
    )

    embedding = EmbeddingModel(
        "configured-model"
    )

    assert len(module.encoders) == 1
    assert module.encoders[0].model_name == "configured-model"
    assert embedding.embed_text("xin chào") == [0.1, 0.2, 0.3]
    assert embedding.embed_text("hello") == [0.1, 0.2, 0.3]
    assert len(module.encoders) == 1


def test_model_name_is_passed_from_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = patch_sentence_transformers(
        monkeypatch
    )
    settings = Settings(
        pos_base_url="http://pos.test",
        embedding_model_name="configured-model",
    )

    EmbeddingModel(
        settings.embedding_model_name
    )

    assert module.encoders[0].model_name == "configured-model"


def test_chunks_use_one_normalized_batch_and_preserve_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = patch_sentence_transformers(
        monkeypatch
    )
    embedding = EmbeddingModel(
        "model"
    )
    chunks = [
        Chunk(
            text="first",
            source="doc.md",
            file_path="knowledge/doc.md",
            chunk_index=0,
        ),
        Chunk(
            text="second",
            source="doc.md",
            file_path="knowledge/doc.md",
            chunk_index=1,
        ),
        Chunk(
            text="third",
            source="doc.md",
            file_path="knowledge/doc.md",
            chunk_index=2,
        ),
    ]

    vectors = embedding.embed_chunks(
        chunks
    )

    assert vectors == [
        [
            0.0,
            0.5,
            1.0,
        ],
        [
            1.0,
            0.5,
            1.0,
        ],
        [
            2.0,
            0.5,
            1.0,
        ],
    ]
    assert module.encoders[0].calls == [
        (
            (
                "first",
                "second",
                "third",
            ),
            True,
        )
    ]
    assert [chunk.text for chunk in chunks] == ["first", "second", "third"]


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_text_is_rejected(
    query: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_sentence_transformers(
        monkeypatch
    )
    embedding = EmbeddingModel(
        "model"
    )

    with pytest.raises(ValueError, match="empty"):
        embedding.embed_text(
            query
        )


def test_importing_app_main_is_still_safe() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.main",
        ],
        check=False,
    )

    assert result.returncode == 0
