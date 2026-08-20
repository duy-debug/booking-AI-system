from dataclasses import dataclass
from typing import Protocol

from app.rag_v1.config import RAGConfig
from app.rag_v1.indexer import KnowledgeIndexer, build_indexer


class KnowledgeGatewayError(Exception):
    """Lỗi gốc cho các lỗi retrieval đã dự đoán được."""


class KnowledgeGatewayUnavailableError(KnowledgeGatewayError):
    """Được raise khi knowledge source chưa sẵn sàng hoặc đang lỗi."""


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Một document liên quan được trả về từ knowledge search."""

    content: str
    score: float
    source: str | None = None


class KnowledgeGateway(Protocol):
    """Contract search knowledge mà dialog/FAQ layer cần dùng."""

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeDocument]:
        """Trả về các knowledge document liên quan tới query."""
        ...


__all__ = [
    "KnowledgeDocument",
    "KnowledgeGateway",
    "KnowledgeGatewayError",
    "KnowledgeGatewayUnavailableError",
    "KnowledgeIndexer",
    "RAGConfig",
    "build_indexer",
]
