"""Integration test for the checked-in customer knowledge document."""

from pathlib import Path

from app.rag.markdown_ingestion import (
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
    assert [chunk.section for chunk in first] == [
        "Demo Knowledge Base",
        "Opening Hours",
        "Cancellation Policy",
        "Pregnancy Policy",
        "Parking",
    ]
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
    assert all(chunk.source == "knowledge/README.md" for chunk in first)
    assert all(not Path(chunk.source).is_absolute() for chunk in first)
    assert "08:00 đến 22:00" in first[1].content
    assert "liên hệ trực tiếp cửa hàng" in first[-1].content
