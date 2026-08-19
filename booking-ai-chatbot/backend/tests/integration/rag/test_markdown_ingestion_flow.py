"""Integration test for the checked-in customer knowledge document."""

from pathlib import Path

from app.knowledge.index.chunker import SectionAwareMarkdownChunker
from app.knowledge.index.loader import MarkdownKnowledgeLoader


def test_checked_in_markdown_loads_into_deterministic_ordered_chunks() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    loader = MarkdownKnowledgeLoader(backend_root / "knowledge")
    chunker = SectionAwareMarkdownChunker()

    first = chunker.chunk_all(loader.load_all())
    repeated = chunker.chunk_all(loader.load_all())

    assert first == repeated
    assert len(first) == 135
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
    assert first[-1].section == "Nguyên tắc phục vụ cuối cùng"
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
    assert all(chunk.source == "knowledge/README.md" for chunk in first)
    assert all(not Path(chunk.source).is_absolute() for chunk in first)
    assert "08 giờ 00" in first[1].content
    assert "22 giờ 00" in first[1].content
    assert "chatbot" in first[-1].content.casefold()
