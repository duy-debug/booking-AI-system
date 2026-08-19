"""Tests for the runtime knowledge reranker."""

import pytest

from app.knowledge import KnowledgeDocument
from app.knowledge.query.service import KnowledgeReranker


def document(content: str, score: float) -> KnowledgeDocument:
    return KnowledgeDocument(content=content, score=score, source="knowledge/README.md")


def test_reranker_prefers_lexical_overlap_over_raw_vector_score() -> None:
    reranker = KnowledgeReranker(top_n=2)
    documents = [
        document("Cancellation policy requires 4 hours notice.", 0.72),
        document("Massage pricing overview for weekday packages.", 0.95),
        document("Cancellation fee is waived for rainstorms.", 0.70),
    ]

    reranked = reranker.rerank(query="cancellation policy fee", documents=documents)

    assert [item.content for item in reranked] == [
        "Cancellation policy requires 4 hours notice.",
        "Cancellation fee is waived for rainstorms.",
    ]


def test_reranker_uses_original_score_as_tie_breaker() -> None:
    reranker = KnowledgeReranker(top_n=2)
    documents = [
        document("Opening hours 08:00 to 22:00.", 0.80),
        document("Opening hours 09:00 to 21:00.", 0.91),
    ]

    reranked = reranker.rerank(query="opening hours", documents=documents)

    assert [item.score for item in reranked] == [0.91, 0.80]


def test_reranker_returns_up_to_top_n_documents() -> None:
    reranker = KnowledgeReranker(top_n=1)

    reranked = reranker.rerank(
        query="parking",
        documents=[
            document("Parking is available at the front gate.", 0.82),
            document("Street parking may be limited on weekends.", 0.79),
        ],
    )

    assert len(reranked) == 1


@pytest.mark.parametrize("query", ["", "  ", "\n\t"])
def test_reranker_rejects_empty_query(query: str) -> None:
    reranker = KnowledgeReranker()

    with pytest.raises(ValueError, match="query"):
        reranker.rerank(query=query, documents=[])


def test_reranker_accepts_empty_document_list() -> None:
    reranker = KnowledgeReranker()

    assert reranker.rerank(query="faq", documents=[]) == []
