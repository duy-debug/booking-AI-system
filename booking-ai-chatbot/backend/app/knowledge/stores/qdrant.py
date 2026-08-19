"""Các helper storage Qdrant dùng cho runtime retrieval và indexing."""

from collections.abc import Sequence
from importlib import import_module
from typing import Protocol, cast

from qdrant_client import QdrantClient, models
from qdrant_client.http.models import CollectionInfo
from qdrant_client.http.models.models import QueryResponse


class QdrantQueryClient(Protocol):
    """Boundary query Qdrant tối thiểu mà knowledge gateway cần."""

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        *,
        limit: int,
        with_payload: bool,
        with_vectors: bool,
    ) -> QueryResponse: ...


class QdrantIndexClient(Protocol):
    """Boundary Qdrant sync tối thiểu mà offline indexer cần."""

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


def normalize_collection_name(collection_name: str) -> str:
    """Trả về Qdrant collection name đã validate."""
    # ----------------------------------------------------
    # STEP 1: Chuẩn hóa collection name
    # ----------------------------------------------------
    #
    # Strip khoảng trắng để tránh tạo hai collection khác nhau chỉ vì
    # input có whitespace ở đầu/cuối.
    # ----------------------------------------------------
    normalized = collection_name.strip()

    # ----------------------------------------------------
    # STEP 2: Chặn collection name rỗng
    # ----------------------------------------------------
    #
    # Qdrant cần tên collection rõ ràng cho cả indexing và retrieval.
    # ----------------------------------------------------
    if not normalized:
        raise ValueError("Qdrant collection name must not be empty.")
    return normalized


def build_qdrant_vector_store(
    client: QdrantQueryClient | QdrantIndexClient,
    collection_name: str,
    *,
    enable_hybrid: bool = False,
) -> object:
    """Tạo LlamaIndex Qdrant vector store cho một collection."""
    # ----------------------------------------------------
    # STEP 1: Import QdrantVectorStore khi thật sự cần
    # ----------------------------------------------------
    #
    # Chỉ khi chạy đường LlamaIndex mới cần dependency này; dense fallback
    # không bắt buộc phải import LlamaIndex.
    # ----------------------------------------------------
    qdrant_module = import_module("llama_index.vector_stores.qdrant")
    qdrant_vector_store = getattr(qdrant_module, "QdrantVectorStore")

    # ----------------------------------------------------
    # STEP 2: Tạo vector store cho collection hiện tại
    # ----------------------------------------------------
    #
    # enable_hybrid=True cho phép LlamaIndex/Qdrant dùng hybrid search
    # dense + sparse khi index/retrieve.
    # ----------------------------------------------------
    return qdrant_vector_store(
        client=cast(object, client),
        collection_name=normalize_collection_name(collection_name),
        enable_hybrid=enable_hybrid,
    )


def build_qdrant_client(
    *,
    host: str,
    port: int,
    api_key: str | None = None,
) -> QdrantClient:
    """Tạo Qdrant client dùng chung cho runtime và indexing flow."""
    # ----------------------------------------------------
    # STEP 1: Tạo Qdrant client dùng chung
    # ----------------------------------------------------
    #
    # Runtime retrieval và offline indexing dùng cùng cách khởi tạo để
    # tránh lệch cấu hình host/port/api_key giữa hai luồng.
    # ----------------------------------------------------
    return QdrantClient(
        host=host,
        port=port,
        api_key=api_key,
    )
