"""Application port for searching relevant knowledge documents."""

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
