"""Các helper ghi Qdrant cho pipeline indexing knowledge offline."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid5

from qdrant_client import models

# Writer nhận KnowledgeChunk từ chunker rồi chuyển thành Qdrant PointStruct.
from app.knowledge.index.chunker import KnowledgeChunk

# Các lỗi này thể hiện lỗi indexing có thể dự đoán được, ví dụ collection
# Qdrant không tương thích hoặc source không tạo được chunk.
from app.knowledge.index.errors import (
    EmptyKnowledgeDocumentError,
    IncompatibleCollectionError,
    InvalidIndexingSourceError,
    KnowledgeIndexingError,
)

# QdrantIndexClient là contract tối thiểu để writer không phụ thuộc trực tiếp
# vào toàn bộ QdrantClient thật trong unit test.
from app.knowledge.stores.qdrant import QdrantIndexClient, normalize_collection_name

_POINT_ID_NAMESPACE = UUID("f3050e37-e832-5c11-9a82-8d86e2251dc9")
# Namespace cố định cho uuid5.
#
# Cùng một chunk_id luôn sinh ra cùng UUID, giúp re-index không tạo point id
# ngẫu nhiên mới trong Qdrant.


class IndexEmbedding(Protocol):
    """Contract embedding tối thiểu mà offline indexer cần."""

    @property
    def dimension(self) -> int: ...
    # Dimension vector sau khi embed, dùng để tạo/validate Qdrant collection.

    def embed_documents(self, texts: list[str] | tuple[str, ...]) -> list[list[float]]: ...
    # Batch embed chunk content và giữ đúng thứ tự input.


@dataclass(frozen=True, slots=True)
class IndexingSummary:
    """Kết quả không nhạy cảm được trả về sau một lượt indexing."""

    # Collection đã được ghi dữ liệu.
    collection_name: str

    # Logical source path của document vừa index.
    source: str

    # Số chunk đã ghi vào Qdrant.
    chunk_count: int

    # Dimension vector dùng trong lượt index.
    vector_dimension: int


def point_id_for_chunk(chunk_id: str) -> str:
    """Trả UUID ổn định, tương thích Qdrant cho một chunk identity."""
    # ----------------------------------------------------
    # STEP 1: Kiểm tra chunk_id
    # ----------------------------------------------------
    #
    # chunk_id là định danh logic do chunker tạo ra.
    #
    # Nếu chunk_id rỗng thì Qdrant point sẽ không có identity ổn định.
    # ----------------------------------------------------
    if not chunk_id:
        raise ValueError("Knowledge chunk ID must not be empty.")

    # ----------------------------------------------------
    # STEP 2: Tạo UUID ổn định cho Qdrant
    # ----------------------------------------------------
    #
    # uuid5 dùng namespace cố định + chunk_id, nên cùng một chunk luôn
    # sinh ra cùng một point id khi re-index.
    # ----------------------------------------------------
    return str(uuid5(_POINT_ID_NAMESPACE, chunk_id))


def ensure_collection(
    *,
    client: QdrantIndexClient,
    collection_name: str,
    vector_dimension: int,
    recreate: bool,
) -> None:
    """Tạo mới hoặc validate collection Qdrant cho knowledge vector."""
    # ----------------------------------------------------
    # STEP 1: Chuẩn hóa collection name
    # ----------------------------------------------------
    #
    # Qdrant collection name không được rỗng. Việc normalize đặt ở đây
    # để mọi writer dùng chung một rule.
    # ----------------------------------------------------
    normalized_collection = normalize_collection_name(collection_name)

    # ----------------------------------------------------
    # STEP 2: Kiểm tra collection hiện có
    # ----------------------------------------------------
    #
    # Nếu collection đã tồn tại và caller yêu cầu recreate, ta xóa trước
    # để schema vector được tạo lại từ đầu.
    # ----------------------------------------------------
    exists = client.collection_exists(normalized_collection)
    if exists and recreate:
        client.delete_collection(normalized_collection)
        exists = False

    # ----------------------------------------------------
    # STEP 3: Tạo collection mới khi chưa tồn tại
    # ----------------------------------------------------
    #
    # Dense mode dùng một unnamed vector với cosine distance, đúng với
    # cách retriever fallback dense query_points() đang query.
    # ----------------------------------------------------
    if not exists:
        client.create_collection(
            collection_name=normalized_collection,
            vectors_config=models.VectorParams(
                size=vector_dimension,
                distance=models.Distance.COSINE,
            ),
        )
        return

    # ----------------------------------------------------
    # STEP 4: Kiểm tra schema collection cũ
    # ----------------------------------------------------
    #
    # Nếu collection đã có sẵn nhưng khác dimension/distance, indexing
    # phải fail sớm để tránh ghi vector vào schema không tương thích.
    # ----------------------------------------------------
    information = client.get_collection(normalized_collection)
    vectors_config = information.config.params.vectors
    if not isinstance(vectors_config, models.VectorParams):
        raise IncompatibleCollectionError("Qdrant collection must use one unnamed dense vector.")
    if vectors_config.size != vector_dimension:
        raise IncompatibleCollectionError(
            "Qdrant collection vector size does not match the embedding model."
        )
    if vectors_config.distance is not models.Distance.COSINE:
        raise IncompatibleCollectionError("Qdrant collection distance must be cosine.")


def source_filter(source: str) -> models.FilterSelector:
    """Build filter selector để thay thế một logical source trong Qdrant."""
    # ----------------------------------------------------
    # STEP 1: Tạo filter theo logical source
    # ----------------------------------------------------
    #
    # Khi re-index một file, ta chỉ xóa các point có cùng source trong
    # payload, không đụng tới tài liệu khác trong cùng collection.
    # ----------------------------------------------------
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


def point_from_chunk(
    *,
    chunk: KnowledgeChunk,
    vector: list[float],
) -> models.PointStruct:
    """Map một chunk và embedding vector của nó thành Qdrant point."""
    # ----------------------------------------------------
    # STEP 1: Chuyển chunk thành Qdrant point
    # ----------------------------------------------------
    #
    # id dùng UUID ổn định từ chunk_id; vector là dense embedding;
    # payload giữ text và metadata để retrieval trả về được nguồn rõ ràng.
    # ----------------------------------------------------
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
