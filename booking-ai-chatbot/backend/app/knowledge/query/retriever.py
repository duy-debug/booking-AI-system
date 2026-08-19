"""Retrieval runtime dùng LlamaIndex trên Qdrant cho knowledge search."""

import asyncio
from collections.abc import Callable, Sequence
from importlib import import_module
import logging
from math import isfinite
from pathlib import PurePosixPath
from threading import Lock
from time import perf_counter
from typing import Any, Protocol, cast

from qdrant_client import models
from qdrant_client.http.exceptions import ApiException

from app.infrastructure.context_store import elapsed_ms, record_turn_metrics, trace_log
from app.knowledge import (
    KnowledgeDocument,
    KnowledgeGatewayUnavailableError,
)
from app.knowledge.embeddings.llamaindex_adapter import build_llamaindex_embedding
from app.knowledge.embeddings.sentence_transformer import SentenceTransformerEmbedding
from app.knowledge.stores.qdrant import (
    QdrantQueryClient,
    build_qdrant_vector_store,
    normalize_collection_name,
)


class RetrieverNode(Protocol):
    """Shape tối thiểu của LlamaIndex node mà gateway cần đọc."""

    @property
    def metadata(self) -> dict[str, object]: ...

    @property
    def text(self) -> str: ...

    @property
    def score(self) -> float | None: ...

    def get_content(self) -> str: ...

    def get_score(self, raise_error: bool = False) -> float: ...


class KnowledgeRetriever(Protocol):
    """Contract retriever tối thiểu dùng chung cho LlamaIndex và test."""

    def retrieve(self, query: str) -> Sequence[RetrieverNode]: ...


class _LlamaIndexRetrieverFactory:
    """Builder lazy cho LlamaIndex index/retriever trên collection Qdrant có sẵn."""

    def __init__(
        self,
        *,
        client: QdrantQueryClient,
        embedding: SentenceTransformerEmbedding,
        collection_name: str,
        hybrid_enabled: bool = False,
        sparse_top_k: int | None = None,
        hybrid_top_k: int | None = None,
    ) -> None:
        self._client = client
        self._embedding = embedding
        self._collection_name = normalize_collection_name(collection_name)
        self._hybrid_enabled = hybrid_enabled
        self._sparse_top_k = sparse_top_k
        self._hybrid_top_k = hybrid_top_k
        self._index: Any | None = None
        self._lock = Lock()

    def build(self, limit: int) -> KnowledgeRetriever:
        # ----------------------------------------------------
        # STEP 1: Lấy LlamaIndex index đã connect Qdrant
        # ----------------------------------------------------
        #
        # Index ở đây không build lại data. Nó chỉ wrap collection Qdrant
        # đã index sẵn để tạo retriever runtime.
        # ----------------------------------------------------
        index = self._get_index()

        # ----------------------------------------------------
        # STEP 2: Tạo retriever kwargs
        # ----------------------------------------------------
        #
        # similarity_top_k là số candidate dense/hybrid muốn lấy về.
        #
        # Khi hybrid bật, LlamaIndex sẽ gửi query mode hybrid xuống
        # QdrantVectorStore để kết hợp dense + sparse.
        # ----------------------------------------------------
        retriever_kwargs: dict[str, object] = {"similarity_top_k": limit}
        if self._hybrid_enabled:
            retriever_kwargs["vector_store_query_mode"] = "hybrid"
            retriever_kwargs["sparse_top_k"] = self._sparse_top_k or max(limit, limit * 2)
            if self._hybrid_top_k is not None:
                retriever_kwargs["hybrid_top_k"] = self._hybrid_top_k
        return cast(KnowledgeRetriever, index.as_retriever(**retriever_kwargs))

    def _get_index(self) -> Any:
        # ----------------------------------------------------
        # STEP 1: Tái sử dụng index đã build
        # ----------------------------------------------------
        #
        # LlamaIndex object được cache để mỗi request không phải dựng lại
        # wrapper quanh Qdrant collection.
        # ----------------------------------------------------
        index = self._index
        if index is not None:
            return index

        # ----------------------------------------------------
        # STEP 2: Lock khi lazy-build index
        # ----------------------------------------------------
        #
        # Lock tránh nhiều request đồng thời cùng import/build LlamaIndex.
        # ----------------------------------------------------
        with self._lock:
            index = self._index
            if index is None:
                # --------------------------------------------
                # STEP 3: Import LlamaIndex và kết nối Qdrant vector store
                # --------------------------------------------
                #
                # from_vector_store() dùng collection đã tồn tại trong Qdrant.
                # Embedding adapter giúp LlamaIndex dùng model của app.
                # --------------------------------------------
                core_module = import_module("llama_index.core")
                vector_store_index = getattr(core_module, "VectorStoreIndex")
                index = vector_store_index.from_vector_store(
                    vector_store=build_qdrant_vector_store(
                        client=self._client,
                        collection_name=self._collection_name,
                        enable_hybrid=self._hybrid_enabled,
                    ),
                    embed_model=build_llamaindex_embedding(self._embedding),
                )
                self._index = index
        return index


class KnowledgeQdrantClient:
    """Retrieve ranked knowledge document qua LlamaIndex trên Qdrant."""

    def __init__(
        self,
        *,
        client: QdrantQueryClient,
        embedding: SentenceTransformerEmbedding,
        collection_name: str,
        retriever_factory: Callable[[int], KnowledgeRetriever] | None = None,
        hybrid_enabled: bool = False,
        sparse_top_k: int | None = None,
        hybrid_top_k: int | None = None,
    ) -> None:
        self._client = client
        self._embedding = embedding
        self._collection_name = normalize_collection_name(collection_name)
        self._retriever_factory = retriever_factory
        self._hybrid_enabled = hybrid_enabled
        self._llama_index = _LlamaIndexRetrieverFactory(
            client=client,
            embedding=embedding,
            collection_name=self._collection_name,
            hybrid_enabled=hybrid_enabled,
            sparse_top_k=sparse_top_k,
            hybrid_top_k=hybrid_top_k,
        )

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeDocument]:
        """
        Search knowledge document cho một user query.

        Luồng:

        query
          -> validate input
          -> chạy sync retrieval trong worker thread
          -> chuyển lỗi provider
          -> trả list[KnowledgeDocument]
        """

        # ----------------------------------------------------
        # STEP 1: Kiểm tra input tìm kiếm
        # ----------------------------------------------------
        #
        # Query phải có nội dung thật và limit phải là số nguyên dương.
        #
        # Bắt lỗi từ caller trước khi đụng tới embedding model,
        # LlamaIndex hoặc Qdrant.
        # ----------------------------------------------------
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Knowledge query must not be empty.")
        if type(limit) is not int or limit <= 0:
            raise ValueError("Knowledge result limit must be a positive integer.")

        # ----------------------------------------------------
        # STEP 2: Bắt đầu trace retrieval
        # ----------------------------------------------------
        #
        # Retrieval có thể gọi Qdrant và có thể lazy-load embedding hoặc
        # LlamaIndex dependency.
        #
        # Trace giúp debug latency và lỗi provider ở production mà không
        # log raw result nhạy cảm.
        # ----------------------------------------------------
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

        # ----------------------------------------------------
        # STEP 3: Chạy retrieval blocking ngoài event loop
        # ----------------------------------------------------
        #
        # SentenceTransformer và Qdrant client ở đây là sync operation.
        #
        # asyncio.to_thread() giúp FastAPI event loop không bị block trong
        # lúc retrieval đang chạy.
        # ----------------------------------------------------
        try:
            documents = await asyncio.to_thread(self._search_sync, query, limit)

        # ----------------------------------------------------
        # STEP 4: Chuyển lỗi hạ tầng Qdrant
        # ----------------------------------------------------
        #
        # Lỗi riêng của Qdrant được chuyển thành lỗi Knowledge Gateway.
        #
        # Layer phía trên có thể render response an toàn mà không cần biết
        # chi tiết nội bộ của Qdrant.
        # ----------------------------------------------------
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

        # ----------------------------------------------------
        # STEP 5: Chuyển lỗi lazy dependency
        # ----------------------------------------------------
        #
        # ImportError/OSError/RuntimeError thường nghĩa là local model,
        # LlamaIndex hoặc embedding runtime đang thiếu/chưa sẵn sàng.
        #
        # Các lỗi này được xem là hạ tầng chưa sẵn sàng, không phải là
        # một FAQ result hợp lệ.
        # ----------------------------------------------------
        except (ImportError, OSError, RuntimeError) as error:
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

        # ----------------------------------------------------
        # STEP 6: Log và trả document
        # ----------------------------------------------------
        #
        # Tới đây toàn bộ kết quả từ provider đã được normalize thành các
        # KnowledgeDocument an toàn.
        # ----------------------------------------------------
        trace_log(
            logging.getLogger(__name__),
            logging.INFO,
            "QdrantClient",
            "qdrant_completed",
            operation="qdrant_search",
            collection=self._collection_name,
            vector_candidate_count=len(documents),
            accepted_result_count=len(documents),
            top_score=documents[0].score if documents else None,
            duration_ms=elapsed_ms(started_at),
        )
        return documents

    def _search_sync(self, query: str, limit: int) -> list[KnowledgeDocument]:
        # ----------------------------------------------------
        # STEP 1: Ưu tiên LlamaIndex retriever
        # ----------------------------------------------------
        #
        # LlamaIndex là đường retrieval chính ở production.
        #
        # Khi bật hybrid search, retriever được build với
        # vector_store_query_mode="hybrid" và Qdrant xử lý dense + sparse
        # search thông qua vector store.
        # ----------------------------------------------------
        retriever = self._build_retriever(limit)
        if retriever is not None:
            return _documents_from_nodes(retriever.retrieve(query))

        # ----------------------------------------------------
        # STEP 2: Fallback sang dense Qdrant
        # ----------------------------------------------------
        #
        # Nếu LlamaIndex chưa được cài, vẫn giữ đường dense search tối
        # thiểu để môi trường local/dev có thể retrieve từ collection chỉ
        # có dense vector.
        #
        # query
        #   -> embedding vector
        #   -> Qdrant query_points()
        #   -> KnowledgeDocument list
        # ----------------------------------------------------
        query_vector = self._embedding.embed_query(query)
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return _documents_from_points(response.points)

    def _build_retriever(self, limit: int) -> KnowledgeRetriever | None:
        # ----------------------------------------------------
        # STEP 1: Dùng test/custom retriever nếu có
        # ----------------------------------------------------
        #
        # retriever_factory giúp unit test inject fake retriever mà không
        # cần chạy LlamaIndex hoặc Qdrant thật.
        # ----------------------------------------------------
        factory = self._retriever_factory
        if factory is not None:
            return factory(limit)

        # ----------------------------------------------------
        # STEP 2: Tạo LlamaIndex retriever mặc định
        # ----------------------------------------------------
        #
        # Nếu thiếu LlamaIndex dependency, trả None để _search_sync fallback
        # sang dense Qdrant path.
        # ----------------------------------------------------
        try:
            return self._llama_index.build(limit)
        except ImportError:
            return None


def _documents_from_nodes(
    nodes: Sequence[RetrieverNode],
) -> list[KnowledgeDocument]:
    """Chuyển LlamaIndex node thành KnowledgeDocument an toàn."""
    # ----------------------------------------------------
    # STEP 1: Duyệt từng node trả về từ LlamaIndex
    # ----------------------------------------------------
    #
    # Node thiếu content, metadata hoặc score hợp lệ sẽ bị bỏ qua để layer
    # trên chỉ nhận dữ liệu đã normalize.
    # ----------------------------------------------------
    documents: list[KnowledgeDocument] = []
    for node in nodes:
        try:
            content = node.get_content()
        except ValueError:
            content = node.text
        if not isinstance(content, str) or not content.strip():
            continue
        metadata = node.metadata
        if not isinstance(metadata, dict):
            continue
        source = metadata.get("source")
        if source is not None and (
            not isinstance(source, str) or not _is_safe_logical_source(source)
        ):
            continue
        score = node.score
        if score is None:
            score = node.get_score()
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


def _documents_from_points(
    points: Sequence[models.ScoredPoint],
) -> list[KnowledgeDocument]:
    """Chuyển Qdrant scored point thành KnowledgeDocument an toàn."""
    # ----------------------------------------------------
    # STEP 1: Duyệt từng point trả về từ dense fallback
    # ----------------------------------------------------
    #
    # Dense fallback đọc content/source từ payload và score từ Qdrant
    # ScoredPoint, sau đó chuẩn hóa về contract chung KnowledgeDocument.
    # ----------------------------------------------------
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
    """Validate logical source để tránh leak unsafe path."""
    # ----------------------------------------------------
    # STEP 1: Chỉ chấp nhận relative POSIX-like path
    # ----------------------------------------------------
    #
    # Source đi ra ngoài response/log nên không được là absolute path,
    # không có backslash và không có "."/".." segment.
    # ----------------------------------------------------
    path = PurePosixPath(source)
    return bool(
        source
        and not path.is_absolute()
        and "\\" not in source
        and all(part not in {"", ".", ".."} for part in path.parts)
    )
