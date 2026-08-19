"""Các building block Knowledge/RAG dùng chung cho chatbot."""

from dataclasses import dataclass
from typing import Protocol


class KnowledgeGatewayError(Exception):
    """Lỗi gốc cho các lỗi retrieval đã dự đoán được."""


class KnowledgeGatewayUnavailableError(KnowledgeGatewayError):
    """Được raise khi knowledge source đang không sẵn sàng."""


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Một document liên quan được trả về từ knowledge search."""

    content: str
    score: float
    source: str | None = None


class KnowledgeGateway(Protocol):
    """Contract search knowledge mà application layer cần dùng."""

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
]
