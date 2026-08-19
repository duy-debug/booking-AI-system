"""Tests for lazy local semantic embeddings."""

import subprocess
import sys
from collections.abc import Sequence

import pytest

from app.infrastructure.context_store import Settings
from app.knowledge.embeddings.sentence_transformer import SentenceTransformerEmbedding


class FakeEncoder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    def encode(
        self,
        sentences: Sequence[str],
        *,
        normalize_embeddings: bool,
    ) -> object:
        supplied = tuple(sentences)
        self.calls.append((supplied, normalize_embeddings))
        return [[float(index), 0.5, 1.0] for index, _ in enumerate(supplied)]

    def get_sentence_embedding_dimension(self) -> int:
        return 3


class RecordingLoader:
    def __init__(self, encoder: FakeEncoder) -> None:
        self.encoder = encoder
        self.model_names: list[str] = []

    def __call__(self, model_name: str) -> FakeEncoder:
        self.model_names.append(model_name)
        return self.encoder


def test_model_is_lazy_loaded_once_and_reused() -> None:
    encoder = FakeEncoder()
    loader = RecordingLoader(encoder)
    embedding = SentenceTransformerEmbedding("configured-model", model_loader=loader)

    assert loader.model_names == []
    with pytest.raises(RuntimeError, match="after"):
        _ = embedding.dimension

    assert embedding.embed_query("xin chào") == [0.0, 0.5, 1.0]
    assert embedding.embed_query("hello") == [0.0, 0.5, 1.0]
    assert loader.model_names == ["configured-model"]
    assert embedding.dimension == 3


def test_model_name_is_passed_from_runtime_config() -> None:
    settings = Settings(
        pos_base_url="http://pos.test",
        embedding_model_name="configured-model",
    )
    loader = RecordingLoader(FakeEncoder())
    embedding = SentenceTransformerEmbedding(
        settings.embedding_model_name,
        model_loader=loader,
    )

    embedding.embed_query("query")

    assert loader.model_names == ["configured-model"]


def test_documents_use_one_normalized_batch_and_preserve_order() -> None:
    encoder = FakeEncoder()
    embedding = SentenceTransformerEmbedding(
        "model",
        model_loader=RecordingLoader(encoder),
    )
    texts = ["first", "second", "third"]

    vectors = embedding.embed_documents(texts)

    assert vectors == [
        [0.0, 0.5, 1.0],
        [1.0, 0.5, 1.0],
        [2.0, 0.5, 1.0],
    ]
    assert encoder.calls == [(tuple(texts), True)]
    assert texts == ["first", "second", "third"]


def test_empty_documents_do_not_load_model() -> None:
    loader = RecordingLoader(FakeEncoder())
    embedding = SentenceTransformerEmbedding("model", model_loader=loader)

    assert embedding.embed_documents([]) == []
    assert loader.model_names == []


@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_empty_query_is_rejected_without_loading_model(query: str) -> None:
    loader = RecordingLoader(FakeEncoder())
    embedding = SentenceTransformerEmbedding("model", model_loader=loader)

    with pytest.raises(ValueError, match="query"):
        embedding.embed_query(query)

    assert loader.model_names == []


def test_invalid_output_count_is_rejected() -> None:
    class MissingVectorEncoder(FakeEncoder):
        def encode(
            self,
            sentences: Sequence[str],
            *,
            normalize_embeddings: bool,
        ) -> object:
            return [[1.0, 2.0, 3.0]]

    embedding = SentenceTransformerEmbedding(
        "model",
        model_loader=RecordingLoader(MissingVectorEncoder()),
    )

    with pytest.raises(ValueError, match="vector count"):
        embedding.embed_documents(["one", "two"])


def test_inconsistent_vector_dimension_is_rejected() -> None:
    class WrongDimensionEncoder(FakeEncoder):
        def encode(
            self,
            sentences: Sequence[str],
            *,
            normalize_embeddings: bool,
        ) -> object:
            return [[1.0, 2.0] for _ in sentences]

    embedding = SentenceTransformerEmbedding(
        "model",
        model_loader=RecordingLoader(WrongDimensionEncoder()),
    )

    with pytest.raises(ValueError, match="dimensions"):
        embedding.embed_query("query")


def test_importing_app_main_does_not_import_sentence_transformers() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app.main; raise SystemExit('sentence_transformers' in sys.modules)",
        ],
        check=False,
    )

    assert result.returncode == 0
