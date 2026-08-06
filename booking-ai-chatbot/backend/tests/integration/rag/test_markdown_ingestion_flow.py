"""Integration test for the checked-in customer knowledge document."""

from pathlib import Path

from app.infrastructure.qdrant_client import (
    MarkdownKnowledgeLoader,
    SectionAwareMarkdownChunker,
)


def test_checked_in_markdown_loads_into_deterministic_ordered_chunks() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    loader = MarkdownKnowledgeLoader(backend_root / "knowledge")
    chunker = SectionAwareMarkdownChunker()

    first = chunker.chunk_all(loader.load_all())
    repeated = chunker.chunk_all(loader.load_all())

    assert first == repeated
    assert len(first) == 71
    assert [chunk.section for chunk in first[:8]] == [
        "Demo Knowledge Base",
        "Opening Hours",
        "Booking Availability",
        "Same-Day Booking",
        "Advance Booking",
        "Group Booking",
        "Single Booking",
        "Therapist Request",
    ]
    assert first[-1].section == "When to Contact the Store"
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
    assert all(chunk.source == "knowledge/README.md" for chunk in first)
    assert all(not Path(chunk.source).is_absolute() for chunk in first)
    assert "08:00" in first[1].content
    assert "22:00" in first[1].content
    assert "chatbot" in first[-1].content
