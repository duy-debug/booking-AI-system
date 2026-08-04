"""Lazy local sentence embeddings for knowledge documents and FAQ queries."""

from collections.abc import Callable, Sequence
from math import isfinite
from threading import Lock
from typing import Protocol, cast


class _SentenceEncoder(Protocol):
    def encode(
        self,
        sentences: Sequence[str],
        *,
        normalize_embeddings: bool,
    ) -> object: ...

    def get_sentence_embedding_dimension(self) -> int | None: ...


EncoderLoader = Callable[[str], _SentenceEncoder]


class SentenceTransformerEmbedding:
    """Embed queries and documents with one lazily loaded local model."""

    def __init__(
        self,
        model_name: str,
        *,
        model_loader: EncoderLoader | None = None,
    ) -> None:
        normalized_model_name = model_name.strip()
        if not normalized_model_name:
            raise ValueError("Embedding model name must not be empty.")
        self._model_name = normalized_model_name
        self._model_loader = model_loader or _load_sentence_transformer
        self._model: _SentenceEncoder | None = None
        self._dimension: int | None = None
        self._load_lock = Lock()

    @property
    def dimension(self) -> int:
        """Return vector dimension after the first embedding operation."""
        if self._dimension is None:
            raise RuntimeError(
                "Embedding dimension is available after the model has encoded text."
            )
        return self._dimension

    def embed_query(self, text: str) -> list[float]:
        """Return one normalized semantic vector for a non-empty query."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding query must not be empty.")
        return self._encode((text,))[0]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Batch-encode documents in their supplied order."""
        document_texts = tuple(texts)
        if not document_texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in document_texts):
            raise ValueError("Embedding documents must contain non-empty text.")
        return self._encode(document_texts)

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._get_model()
        raw_vectors = model.encode(
            texts,
            normalize_embeddings=True,
        )
        vectors = _coerce_vectors(raw_vectors)
        if len(vectors) != len(texts):
            raise ValueError("Embedding model returned an unexpected vector count.")
        model_dimension = model.get_sentence_embedding_dimension()
        if type(model_dimension) is not int or model_dimension <= 0:
            raise ValueError("Embedding model returned an invalid vector dimension.")
        if any(len(vector) != model_dimension for vector in vectors):
            raise ValueError("Embedding model returned inconsistent vector dimensions.")
        self._dimension = model_dimension
        return vectors

    def _get_model(self) -> _SentenceEncoder:
        model = self._model
        if model is not None:
            return model
        with self._load_lock:
            model = self._model
            if model is None:
                model = self._model_loader(self._model_name)
                self._model = model
        return model


def _load_sentence_transformer(model_name: str) -> _SentenceEncoder:
    from sentence_transformers import SentenceTransformer

    return cast(
        _SentenceEncoder,
        SentenceTransformer(model_name, local_files_only=True),
    )


def _coerce_vectors(raw_vectors: object) -> list[list[float]]:
    converter = getattr(raw_vectors, "tolist", None)
    converted = converter() if callable(converter) else raw_vectors
    if not isinstance(converted, Sequence) or isinstance(converted, str | bytes):
        raise ValueError("Embedding model returned an invalid vector collection.")
    vectors: list[list[float]] = []
    for raw_vector in converted:
        if not isinstance(raw_vector, Sequence) or isinstance(raw_vector, str | bytes):
            raise ValueError("Embedding model returned an invalid vector.")
        vector = [float(value) for value in raw_vector]
        if not all(isfinite(value) for value in vector):
            raise ValueError("Embedding model returned a non-finite vector value.")
        vectors.append(vector)
    return vectors
