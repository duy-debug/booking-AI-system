"""Integration test cho flat rag_v1 loader/chunker trên knowledge checked-in."""

from pathlib import Path

from app.rag_v1.chunker import DocumentChunker
from app.rag_v1.loader import DocumentLoader


def test_checked_in_knowledge_loads_into_ordered_chunks() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    loader = DocumentLoader()
    chunker = DocumentChunker()

    first = chunker.chunk_documents(loader.load_directory(backend_root / "knowledge"))
    repeated = chunker.chunk_documents(loader.load_directory(backend_root / "knowledge"))

    assert first == repeated
    assert len(first) > 0
    assert first[0].source
    assert any(chunk.source.endswith(".pdf") for chunk in first)
    assert all(not Path(chunk.source).is_absolute() for chunk in first)
