"""Integration test cho các knowledge document đang được check-in."""

from collections import Counter
from pathlib import Path

from app.knowledge.index.chunker import SectionAwareMarkdownChunker
from app.knowledge.index.loader import MarkdownKnowledgeLoader


def test_checked_in_knowledge_loads_into_deterministic_ordered_chunks() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    loader = MarkdownKnowledgeLoader(backend_root / "knowledge")
    chunker = SectionAwareMarkdownChunker()

    first = chunker.chunk_all(loader.load_all())
    repeated = chunker.chunk_all(loader.load_all())

    assert first == repeated
    assert len(first) == 174
    assert Counter(chunk.source for chunk in first) == {
        "knowledge/README.md": 135,
        "knowledge/[Description-v1]-Project-1.2-RAG-Chatbot.pdf": 39,
    }
    assert [chunk.section for chunk in first[:8]] == [
        "Cơ sở tri thức mẫu cho chatbot đặt lịch massage",
        "Giờ hoạt động của cửa hàng",
        "Thời gian nhận khách cuối cùng",
        "Thay đổi giờ hoạt động",
        "Đặt lịch trước",
        "Đặt lịch trong ngày",
        "Đặt lịch sát giờ sử dụng dịch vụ",
        "Giá trị của khung giờ còn trống",
    ]
    assert first[134].section == "Nguyên tắc phục vụ cuối cùng"
    assert first[-1].source == "knowledge/[Description-v1]-Project-1.2-RAG-Chatbot.pdf"
    assert [chunk.chunk_index for chunk in first[:135]] == list(range(135))
    assert [chunk.chunk_index for chunk in first[135:]] == list(range(39))
    assert all(chunk.source == "knowledge/README.md" for chunk in first[:135])
    assert all(not Path(chunk.source).is_absolute() for chunk in first)
    assert "08 giờ 00" in first[1].content
    assert "22 giờ 00" in first[1].content
    assert "chatbot" in first[134].content.casefold()
