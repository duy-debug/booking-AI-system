"""Tests for flat rag_v1 loading and chunking."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.rag_v1.chunker import Chunk, DocumentChunker
from app.rag_v1.loader import Document, DocumentLoader


class FakePdfPage:
    def __init__(self, text: str | None) -> None:
        self._text = text

    def extract_text(self) -> str | None:
        return self._text


class FakePdfReader:
    pages = [
        FakePdfPage("Trang 1: Chính sách đặt lịch."),
        FakePdfPage(None),
        FakePdfPage("Trang 2: Chính sách hủy lịch."),
    ]

    def __init__(self, path: Path) -> None:
        self.path = path


def test_loads_markdown_and_normalizes_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "faq.md"
    path.write_bytes("# FAQ\r\n\r\nMở lúc 08:00.\r".encode())

    document = DocumentLoader().load_file(path)

    assert document == Document(
        text="# FAQ\n\nMở lúc 08:00.\n",
        source="faq.md",
        file_path=str(path),
    )


def test_loads_pdf_by_extracting_page_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "policy.pdf"
    path.write_bytes(b"%PDF fake")
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakePdfReader))

    document = DocumentLoader().load_file(path)

    assert document.text == "Trang 1: Chính sách đặt lịch.\n\nTrang 2: Chính sách hủy lịch."
    assert document.source == "policy.pdf"


def test_rejects_unsupported_file(tmp_path: Path) -> None:
    path = tmp_path / "secret.exe"
    path.write_text("private", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported"):
        DocumentLoader().load_file(path)


def test_load_directory_is_recursive_and_sorted(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / "z.md").write_text("Z", encoding="utf-8")
    (root / "a.md").write_text("A", encoding="utf-8")
    (nested / "b.txt").write_text("B", encoding="utf-8")
    (root / "ignored.exe").write_text("ignored", encoding="utf-8")

    documents = DocumentLoader().load_directory(root)

    assert [document.source for document in documents] == ["a.md", "z.md"]


def test_chunker_uses_simple_sliding_window_with_overlap() -> None:
    document = Document(text="abcdefghij", source="faq.md", file_path="knowledge/faq.md")

    chunks = DocumentChunker(chunk_size=4, chunk_overlap=1).chunk_document(document)

    assert chunks == [
        Chunk("abcd", "faq.md", "knowledge/faq.md", 0),
        Chunk("defg", "faq.md", "knowledge/faq.md", 1),
        Chunk("ghij", "faq.md", "knowledge/faq.md", 2),
        Chunk("j", "faq.md", "knowledge/faq.md", 3),
    ]


def test_chunk_documents_flattens_all_documents() -> None:
    documents = [
        Document(text="abc", source="a.md", file_path="a.md"),
        Document(text="def", source="b.md", file_path="b.md"),
    ]

    chunks = DocumentChunker(chunk_size=10, chunk_overlap=0).chunk_documents(documents)

    assert [chunk.text for chunk in chunks] == ["abc", "def"]
