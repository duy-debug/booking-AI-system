"""Application port for searching relevant knowledge documents."""

from dataclasses import dataclass
from typing import Protocol


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
