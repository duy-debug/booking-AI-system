"""Contract tests for the knowledge gateway port."""

from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING

import pytest

from app.infrastructure.qdrant_client import (
    KnowledgeDocument,
    KnowledgeGateway,
)

DOCUMENT = KnowledgeDocument(
    content="The spa is open from 9:00 to 21:00.",
    score=0.95,
    source="opening-hours",
)


class FakeKnowledgeGateway:
    """In-memory fake implementing the knowledge gateway contract."""

    def __init__(self) -> None:
        self.received_limit: int | None = None

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeDocument]:
        self.received_limit = limit
        return [DOCUMENT]


class IncompleteKnowledgeGateway:
    """Fake that intentionally does not satisfy the gateway protocol."""


if TYPE_CHECKING:
    valid_gateway: KnowledgeGateway = FakeKnowledgeGateway()
    invalid_gateway: KnowledgeGateway = IncompleteKnowledgeGateway()  # type: ignore[assignment]


def use_knowledge_gateway(gateway: KnowledgeGateway) -> KnowledgeGateway:
    """Accept the abstraction consumed by application courses."""
    return gateway


def test_create_knowledge_document_with_all_data() -> None:
    assert DOCUMENT.content == "The spa is open from 9:00 to 21:00."
    assert DOCUMENT.score == 0.95
    assert DOCUMENT.source == "opening-hours"


def test_knowledge_document_source_defaults_to_none() -> None:
    document = KnowledgeDocument(content="FAQ content", score=0.8)

    assert document.source is None


def test_knowledge_document_is_immutable() -> None:
    document = KnowledgeDocument(content="FAQ content", score=0.8)

    with pytest.raises(FrozenInstanceError):
        document.score = 0.5  # type: ignore[misc]


def test_knowledge_documents_with_same_data_are_equal() -> None:
    assert DOCUMENT == KnowledgeDocument(
        content="The spa is open from 9:00 to 21:00.",
        score=0.95,
        source="opening-hours",
    )


def test_slots_prevent_adding_undeclared_fields() -> None:
    document = KnowledgeDocument(content="FAQ content", score=0.8)

    assert not hasattr(document, "__dict__")
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(document, "unexpected", "value")


def test_complete_fake_is_accepted_as_knowledge_gateway() -> None:
    gateway = use_knowledge_gateway(FakeKnowledgeGateway())

    assert isinstance(gateway, FakeKnowledgeGateway)


@pytest.mark.asyncio
async def test_fake_search_returns_documents_and_receives_limit() -> None:
    fake = FakeKnowledgeGateway()
    gateway: KnowledgeGateway = fake

    result = await gateway.search("When does the spa open?", limit=3)

    assert isinstance(result, list)
    assert all(isinstance(document, KnowledgeDocument) for document in result)
    assert result == [DOCUMENT]
    assert fake.received_limit == 3
