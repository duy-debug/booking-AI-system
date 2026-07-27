from __future__ import annotations

from typing import Any
from uuid import uuid4

from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings
from app.core.exceptions import AppError
from app.integrations.qdrant import get_qdrant
from app.rag.embeddings import embed_documents, embed_text


# Đảm bảo collection tồn tại trước khi seed tài liệu.
async def ensure_collection() -> None:
    try:
        client = await get_qdrant()
        collections = await client.get_collections()
        names = {item.name for item in collections.collections}
        if settings.QDRANT_COLLECTION not in names:
            await client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=settings.EMBED_DIM,
                    distance=Distance.COSINE,
                ),
            )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            503,
            code="KNOWLEDGE_BASE_UNAVAILABLE",
            detail="Kho kiến thức đang tạm thời không khả dụng.",
        ) from exc


# Ghi các knowledge chunk và metadata nguồn vào Qdrant.
async def upsert_chunks(chunks: list[dict[str, Any]]) -> int:
    if not chunks:
        return 0
    try:
        await ensure_collection()
        client = await get_qdrant()
        vectors = embed_documents([str(chunk["content"]) for chunk in chunks])
        points = [
            PointStruct(id=str(uuid4()), vector=vector, payload=chunk)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points,
            wait=True,
        )
        return len(points)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            503,
            code="KNOWLEDGE_BASE_UNAVAILABLE",
            detail="Không thể cập nhật kho kiến thức.",
        ) from exc


# Tìm các đoạn tri thức gần nhất và chỉ trả dữ liệu cần cho tầng application.
async def search_chunks(query: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        client = await get_qdrant()
        response = await client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=embed_text(query),
            limit=limit,
            with_payload=True,
            score_threshold=0.35,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            503,
            code="KNOWLEDGE_BASE_UNAVAILABLE",
            detail="Kho kiến thức đang tạm thời không khả dụng.",
        ) from exc
    return [
        {
            "id": str(item.id),
            "score": float(item.score),
            **(item.payload or {}),
        }
        for item in response.points
    ]


# Đếm tổng số knowledge chunk để phục vụ health và quản trị knowledge base.
async def count_chunks() -> int:
    try:
        client = await get_qdrant()
        collection = await client.get_collection(settings.QDRANT_COLLECTION)
        return int(collection.points_count or 0)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            503,
            code="KNOWLEDGE_BASE_UNAVAILABLE",
            detail="Kho kiến thức đang tạm thời không khả dụng.",
        ) from exc
