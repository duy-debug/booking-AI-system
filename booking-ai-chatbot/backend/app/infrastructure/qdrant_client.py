"""Application port for searching relevant knowledge documents."""
# ruff: noqa: E402

from dataclasses import dataclass
from typing import Protocol


class KnowledgeGatewayError(Exception):
    """Base exception for expected knowledge retrieval failures."""


class KnowledgeGatewayUnavailableError(KnowledgeGatewayError):
    """Raised when the configured knowledge source is unavailable."""


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Represents a relevant document returned by knowledge search."""

    content: str
    score: float
    source: str | None = None


class KnowledgeGateway(Protocol):
    """Defines knowledge search required by the application layer."""

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeDocument]:
        """Return knowledge documents relevant to a search query."""
        ...

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

"""Qdrant-backed semantic knowledge retrieval."""

import asyncio
import logging
from collections.abc import Sequence
from pathlib import PurePosixPath
from time import perf_counter
from typing import Protocol

from qdrant_client import models
from qdrant_client.http.exceptions import ApiException
from qdrant_client.http.models.models import QueryResponse

from app.infrastructure.context_store import elapsed_ms, record_turn_metrics, trace_log


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


class KnowledgeQdrantClient:
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
        started_at = perf_counter()
        record_turn_metrics(qdrant_calls=1)
        trace_log(
            logging.getLogger(__name__),
            logging.DEBUG,
            "QdrantClient",
            "qdrant_started",
            operation="qdrant_search",
            function="search",
            collection=self._collection_name,
            input_summary={"query_length": len(query), "limit": limit},
            status="started",
        )
        try:
            documents = await asyncio.to_thread(self._search_sync, query, limit)
        except ApiException as error:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "QdrantClient",
                "qdrant_failed",
                operation="qdrant_search",
                collection=self._collection_name,
                error_code="qdrant_unavailable",
                duration_ms=elapsed_ms(started_at),
            )
            raise KnowledgeGatewayUnavailableError(
                "Knowledge retrieval infrastructure is unavailable."
            ) from error
        except (OSError, RuntimeError) as error:
            trace_log(
                logging.getLogger(__name__),
                logging.WARNING,
                "QdrantClient",
                "qdrant_failed",
                operation="qdrant_search",
                collection=self._collection_name,
                error_code="embedding_failure",
                duration_ms=elapsed_ms(started_at),
            )
            raise KnowledgeGatewayUnavailableError(
                "Knowledge embedding infrastructure is unavailable."
            ) from error
        trace_log(
            logging.getLogger(__name__),
            logging.INFO,
            "QdrantClient",
            "qdrant_completed",
            operation="qdrant_search",
            collection=self._collection_name,
            vector_candidate_count=len(documents),
            lexical_candidate_count=0,
            accepted_result_count=len(documents),
            top_score=documents[0].score if documents else None,
            duration_ms=elapsed_ms(started_at),
        )
        return documents

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

"""Load and section-aware chunk trusted Markdown knowledge documents."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_CHUNK_SIZE = 1_000
DEFAULT_MAX_FILE_SIZE = 2 * 1024 * 1024

_ATX_HEADING_PATTERN = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")
_PARAGRAPH_BREAK_PATTERN = re.compile(r"\n[ \t]*\n+")


class KnowledgeIngestionError(Exception):
    """Base error for offline knowledge-document ingestion failures."""


class InvalidKnowledgeRootError(KnowledgeIngestionError):
    """Raised when the configured knowledge root is not a readable directory."""


class InvalidKnowledgePathError(KnowledgeIngestionError):
    """Raised when a document path escapes the configured knowledge root."""


class UnsupportedKnowledgeFileError(KnowledgeIngestionError):
    """Raised when a requested knowledge document is not a Markdown file."""


class KnowledgeFileTooLargeError(KnowledgeIngestionError):
    """Raised when a knowledge document exceeds the configured size limit."""


class InvalidKnowledgeEncodingError(KnowledgeIngestionError):
    """Raised when a knowledge document is not valid UTF-8 text."""


class InvalidKnowledgeContentError(KnowledgeIngestionError):
    """Raised when a knowledge document contains unsupported binary content."""


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """Contains normalized Markdown text and its safe relative source path."""

    content: str
    source: str


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """Represents one deterministic, embedding-ready knowledge text chunk."""

    chunk_id: str
    content: str
    source: str
    section: str | None
    chunk_index: int


@dataclass(frozen=True, slots=True)
class _MarkdownSection:
    heading: str | None
    body: str


class MarkdownKnowledgeLoader:
    """Load UTF-8 Markdown documents confined to one knowledge directory."""

    def __init__(
        self,
        knowledge_root: Path,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        if type(max_file_size) is not int or max_file_size <= 0:
            raise ValueError("Knowledge file size limit must be a positive integer.")
        root = knowledge_root.resolve()
        if not root.is_dir():
            raise InvalidKnowledgeRootError(
                "Knowledge root must be an existing directory."
            )
        self._root = root
        self._max_file_size = max_file_size

    def load(self, path: Path) -> MarkdownDocument:
        """Load one Markdown file without allowing access outside the root."""
        document_path = self._resolve_document_path(path)
        if document_path.suffix.lower() != ".md":
            raise UnsupportedKnowledgeFileError(
                "Knowledge loader accepts only Markdown files."
            )
        if not document_path.is_file():
            raise InvalidKnowledgePathError(
                "Knowledge document must be an existing regular file."
            )
        if document_path.stat().st_size > self._max_file_size:
            raise KnowledgeFileTooLargeError(
                "Knowledge document exceeds the configured size limit."
            )
        raw_content = document_path.read_bytes()
        if len(raw_content) > self._max_file_size:
            raise KnowledgeFileTooLargeError(
                "Knowledge document exceeds the configured size limit."
            )
        if b"\x00" in raw_content:
            raise InvalidKnowledgeContentError(
                "Knowledge document must contain text rather than binary data."
            )
        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InvalidKnowledgeEncodingError(
                "Knowledge document must use UTF-8 encoding."
            ) from error
        normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
        relative_path = document_path.relative_to(self._root).as_posix()
        source = PurePosixPath(self._root.name, relative_path).as_posix()
        return MarkdownDocument(content=normalized_content, source=source)

    def load_all(self) -> list[MarkdownDocument]:
        """Load all Markdown files in deterministic relative-path order."""
        paths = sorted(
            (
                path
                for path in self._root.rglob("*")
                if path.is_file() and path.suffix.lower() == ".md"
            ),
            key=lambda path: path.relative_to(self._root).as_posix(),
        )
        return [self.load(path) for path in paths]

    def _resolve_document_path(self, path: Path) -> Path:
        candidate = path if path.is_absolute() else self._root / path
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._root):
            raise InvalidKnowledgePathError(
                "Knowledge document must remain inside the configured root."
            )
        return resolved


class SectionAwareMarkdownChunker:
    """Split Markdown by headings, paragraphs, and finally bounded word groups."""

    def __init__(self, *, max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE) -> None:
        if type(max_chunk_size) is not int or max_chunk_size < 64:
            raise ValueError("Maximum chunk size must be an integer of at least 64.")
        self._max_chunk_size = max_chunk_size

    def chunk(self, document: MarkdownDocument) -> list[KnowledgeChunk]:
        """Create ordered chunks for one normalized Markdown document."""
        _validate_source(document.source)
        chunks: list[KnowledgeChunk] = []
        for section in _extract_sections(document.content):
            prefix = f"# {section.heading}\n\n" if section.heading else ""
            available_size = self._max_chunk_size - len(prefix)
            if available_size < 1:
                raise InvalidKnowledgeContentError(
                    "Markdown heading leaves no room for section content."
                )
            for body in _split_section_body(section.body, available_size):
                content = f"{prefix}{body}" if prefix else body
                chunk_index = len(chunks)
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=_chunk_id(
                            source=document.source,
                            section=section.heading,
                            chunk_index=chunk_index,
                            content=content,
                        ),
                        content=content,
                        source=document.source,
                        section=section.heading,
                        chunk_index=chunk_index,
                    )
                )
        return chunks

    def chunk_all(
        self,
        documents: list[MarkdownDocument],
    ) -> list[KnowledgeChunk]:
        """Chunk documents in their supplied deterministic order."""
        return [chunk for document in documents for chunk in self.chunk(document)]


def _extract_sections(content: str) -> tuple[_MarkdownSection, ...]:
    sections: list[_MarkdownSection] = []
    heading: str | None = None
    body_lines: list[str] = []
    fence_marker: str | None = None

    def append_section() -> None:
        body = "\n".join(body_lines).strip()
        if body:
            sections.append(_MarkdownSection(heading=heading, body=body))

    for line in content.split("\n"):
        stripped = line.lstrip()
        current_fence = _fence_marker(stripped)
        if current_fence is not None:
            if fence_marker is None:
                fence_marker = current_fence
            elif current_fence == fence_marker:
                fence_marker = None
            body_lines.append(line)
            continue
        match = _ATX_HEADING_PATTERN.fullmatch(line)
        if match is not None and fence_marker is None:
            append_section()
            heading = match.group(1).strip()
            body_lines = []
            continue
        body_lines.append(line)
    append_section()
    return tuple(sections)


def _fence_marker(line: str) -> str | None:
    if line.startswith("```"):
        return "`"
    if line.startswith("~~~"):
        return "~"
    return None


def _split_section_body(body: str, max_size: int) -> tuple[str, ...]:
    paragraphs = tuple(
        normalized
        for paragraph in _PARAGRAPH_BREAK_PATTERN.split(body)
        if (normalized := _normalize_paragraph(paragraph))
    )
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_paragraph(paragraph, max_size))
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_size:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return tuple(chunks)


def _normalize_paragraph(paragraph: str) -> str:
    return "\n".join(line.rstrip() for line in paragraph.strip().split("\n")).strip()


def _split_long_paragraph(paragraph: str, max_size: int) -> tuple[str, ...]:
    words = paragraph.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(word) <= max_size:
                current = word
            else:
                chunks.extend(
                    word[index : index + max_size]
                    for index in range(0, len(word), max_size)
                )
                current = ""
    if current:
        chunks.append(current)
    return tuple(chunks)


def _chunk_id(
    *,
    source: str,
    section: str | None,
    chunk_index: int,
    content: str,
) -> str:
    identity = "\x00".join((source, section or "", str(chunk_index), content))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"kc_{digest[:24]}"


def _validate_source(source: str) -> None:
    path = PurePosixPath(source)
    if (
        not source
        or path.is_absolute()
        or "\\" in source
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise InvalidKnowledgePathError(
            "Knowledge source must be a safe relative POSIX path."
        )

"""Manually index one Markdown knowledge document into Qdrant."""

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid5

from qdrant_client import QdrantClient, models
from qdrant_client.http.models import CollectionInfo

from app.infrastructure.context_store import Settings

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

"""Coordinate deterministic FAQ retrieval outside the booking state machine."""


from app.dialog.instruction_builder import DialogResponse, InstructionBuilder
from app.domain.booking_context import BookingContext

_FAQ_UNAVAILABLE_TEXT = (
    "Hiện tại hệ thống chưa thể tra cứu thông tin này. "
    "Vui lòng liên hệ cửa hàng để được hỗ trợ."
)
_FAQ_NO_RESULT_TEXT = (
    "Hiện tại tôi chưa có đủ thông tin để trả lời câu hỏi này. "
    "Bạn có thể liên hệ cửa hàng để được hỗ trợ."
)
_MAX_DOCUMENTS = 3
_MAX_ANSWER_CHARS = 2_000
_LOGGER = logging.getLogger(__name__)


class FAQManager:
    """Own the FAQ retrieval policy without mutating booking context."""

    def __init__(
        self,
        *,
        knowledge_gateway: KnowledgeGateway | None,
        instruction_builder: InstructionBuilder,
        min_relevance_score: float = 0.45,
    ) -> None:
        if (
            isinstance(min_relevance_score, bool)
            or not isinstance(min_relevance_score, int | float)
            or not 0.0 <= min_relevance_score <= 1.0
        ):
            raise ValueError("FAQ relevance threshold must be between zero and one.")
        self._knowledge_gateway = knowledge_gateway
        self._instruction_builder = instruction_builder
        self._min_relevance_score = float(min_relevance_score)

    async def answer(
        self,
        *,
        query: str,
        context: BookingContext,
    ) -> DialogResponse:
        """Retrieve and render one FAQ answer while preserving booking state."""
        started_at = perf_counter()
        gateway = self._knowledge_gateway
        if gateway is None:
            self._log_failure("qdrant_disabled", started_at)
            return self._render_unavailable(context)
        try:
            documents = await gateway.search(query, limit=_MAX_DOCUMENTS)
        except KnowledgeGatewayError:
            self._log_failure("knowledge_gateway_unavailable", started_at)
            return self._render_unavailable(context)
        accepted = [
            document
            for document in documents
            if document.score >= self._min_relevance_score
        ]
        top_score = max((document.score for document in documents), default=None)
        contents = _document_contents(accepted)
        if not contents:
            trace_log(
                _LOGGER,
                logging.INFO,
                "Knowledge",
                "no_result",
                operation="faq_retrieval",
                candidate_count=len(documents),
                accepted_result_count=0,
                top_score=top_score,
                error_code="no_relevant_result",
                duration_ms=elapsed_ms(started_at),
            )
            return self._instruction_builder.build_faq_response(
                answer=_FAQ_NO_RESULT_TEXT,
                source_count=0,
                context=context,
                handled_failure=True,
            )
        trace_log(
            _LOGGER,
            logging.INFO,
            "Knowledge",
            "completed",
            operation="faq_retrieval",
            candidate_count=len(documents),
            accepted_result_count=len(contents),
            top_score=top_score,
            duration_ms=elapsed_ms(started_at),
        )
        return self._instruction_builder.build_faq_response(
            answer="\n\n".join(contents),
            source_count=len(contents),
            context=context,
        )

    @staticmethod
    def _log_failure(error_code: str, started_at: float) -> None:
        trace_log(
            _LOGGER,
            logging.WARNING,
            "Knowledge",
            "failed",
            operation="faq_retrieval",
            error_code=error_code,
            duration_ms=elapsed_ms(started_at),
        )

    def _render_unavailable(self, context: BookingContext) -> DialogResponse:
        return self._instruction_builder.build_faq_response(
            answer=_FAQ_UNAVAILABLE_TEXT,
            source_count=0,
            context=context,
            handled_failure=True,
        )


def _document_contents(
    documents: list[KnowledgeDocument],
) -> tuple[str, ...]:
    contents: list[str] = []
    seen: set[str] = set()
    current_length = 0
    for document in documents[:_MAX_DOCUMENTS]:
        if not isinstance(document, KnowledgeDocument) or not isinstance(
            document.content, str
        ):
            continue
        content = " ".join(document.content.split())
        deduplication_key = content.casefold()
        if not content or deduplication_key in seen:
            continue
        separator_length = 2 if contents else 0
        remaining = _MAX_ANSWER_CHARS - current_length - separator_length
        if remaining <= 0:
            break
        normalized = content[:remaining].rstrip()
        if not normalized:
            break
        contents.append(normalized)
        seen.add(deduplication_key)
        current_length += separator_length + len(normalized)
    return tuple(contents)
