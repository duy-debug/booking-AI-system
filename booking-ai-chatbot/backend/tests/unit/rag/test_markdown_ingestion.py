"""Unit tests for secure Markdown loading and section-aware chunking."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.infrastructure.qdrant_client import (
    InvalidKnowledgeContentError,
    InvalidKnowledgeEncodingError,
    InvalidKnowledgePathError,
    KnowledgeChunk,
    KnowledgeFileTooLargeError,
    MarkdownDocument,
    MarkdownKnowledgeLoader,
    SectionAwareMarkdownChunker,
    UnsupportedKnowledgeFileError,
)


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    root.mkdir()
    return root


def test_loads_utf8_markdown_and_normalizes_line_endings(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "faq.md").write_bytes("# Giờ mở cửa\r\n\r\nMở lúc 08:00.\r".encode())

    document = MarkdownKnowledgeLoader(root).load(Path("faq.md"))

    assert document == MarkdownDocument(
        content="# Giờ mở cửa\n\nMở lúc 08:00.\n",
        source="knowledge/faq.md",
    )


def test_rejects_non_markdown_file(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "secret.txt").write_text("not knowledge", encoding="utf-8")

    with pytest.raises(UnsupportedKnowledgeFileError):
        MarkdownKnowledgeLoader(root).load(Path("secret.txt"))


def test_rejects_path_traversal_and_absolute_path_outside_root(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    loader = MarkdownKnowledgeLoader(root)

    with pytest.raises(InvalidKnowledgePathError):
        loader.load(Path("../outside.md"))
    with pytest.raises(InvalidKnowledgePathError):
        loader.load(outside)


def test_extracts_headings_and_preserves_section_order() -> None:
    document = MarkdownDocument(
        content=(
            "Preamble.\n\n# Opening Hours\n\nOpen at 08:00.\n\n"
            "## Parking\n\nParking is unconfirmed."
        ),
        source="knowledge/faq.md",
    )

    chunks = SectionAwareMarkdownChunker().chunk(document)

    assert [chunk.section for chunk in chunks] == [None, "Opening Hours", "Parking"]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert chunks[0].content == "Preamble."
    assert chunks[1].content == "# Opening Hours\n\nOpen at 08:00."
    assert chunks[2].content == "# Parking\n\nParking is unconfirmed."


def test_long_section_splits_by_words_without_empty_chunks() -> None:
    body = " ".join(f"word{index}" for index in range(100))
    document = MarkdownDocument(
        content=f"# Long Policy\n\n{body}",
        source="knowledge/long.md",
    )

    chunks = SectionAwareMarkdownChunker(max_chunk_size=120).chunk(document)

    assert len(chunks) > 1
    assert all(chunk.content.strip() for chunk in chunks)
    assert all(len(chunk.content) <= 120 for chunk in chunks)
    assert all(chunk.content.startswith("# Long Policy\n\n") for chunk in chunks)
    reconstructed = " ".join(
        chunk.content.removeprefix("# Long Policy\n\n") for chunk in chunks
    )
    assert reconstructed == body


def test_chunk_ids_are_deterministic_and_change_with_content() -> None:
    chunker = SectionAwareMarkdownChunker()
    original = MarkdownDocument("# Policy\n\nOriginal content.", "knowledge/faq.md")
    changed = MarkdownDocument("# Policy\n\nChanged content.", "knowledge/faq.md")

    first = chunker.chunk(original)
    repeated = chunker.chunk(original)
    updated = chunker.chunk(changed)

    assert first == repeated
    assert first[0].chunk_id != updated[0].chunk_id
    assert first[0].chunk_id.startswith("kc_")


def test_chunk_is_immutable_and_source_never_leaks_absolute_path() -> None:
    document = MarkdownDocument("# FAQ\n\nAnswer.", "knowledge/faq.md")
    chunk = SectionAwareMarkdownChunker().chunk(document)[0]

    assert isinstance(chunk, KnowledgeChunk)
    assert chunk.source == "knowledge/faq.md"
    assert not Path(chunk.source).is_absolute()
    with pytest.raises(FrozenInstanceError):
        chunk.content = "changed"  # type: ignore[misc]


def test_duplicate_headings_remain_ordered_with_unique_indices() -> None:
    document = MarkdownDocument(
        "# Policy\n\nRepeated content.\n\n# Policy\n\nRepeated content.",
        "knowledge/duplicate.md",
    )

    chunks = SectionAwareMarkdownChunker().chunk(document)

    assert [chunk.section for chunk in chunks] == ["Policy", "Policy"]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert chunks[0].content == chunks[1].content
    assert len({chunk.chunk_id for chunk in chunks}) == 2


def test_empty_file_and_heading_only_section_create_no_chunks(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "empty.md").write_text("", encoding="utf-8")
    (root / "heading.md").write_text("# Empty Section\n", encoding="utf-8")
    loader = MarkdownKnowledgeLoader(root)
    chunker = SectionAwareMarkdownChunker()

    assert chunker.chunk(loader.load(Path("empty.md"))) == []
    assert chunker.chunk(loader.load(Path("heading.md"))) == []


def test_rejects_invalid_utf8_and_binary_content(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "invalid.md").write_bytes(b"\xff\xfe")
    (root / "binary.md").write_bytes(b"valid\x00text")
    loader = MarkdownKnowledgeLoader(root)

    with pytest.raises(InvalidKnowledgeEncodingError):
        loader.load(Path("invalid.md"))
    with pytest.raises(InvalidKnowledgeContentError):
        loader.load(Path("binary.md"))


def test_rejects_file_above_configured_size_limit(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    (root / "large.md").write_text("12345", encoding="utf-8")

    with pytest.raises(KnowledgeFileTooLargeError):
        MarkdownKnowledgeLoader(root, max_file_size=4).load(Path("large.md"))


def test_load_all_sorts_by_relative_path_and_ignores_non_markdown(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    nested = root / "nested"
    nested.mkdir()
    (root / "z.md").write_text("Z", encoding="utf-8")
    (root / "a.md").write_text("A", encoding="utf-8")
    (nested / "b.MD").write_text("B", encoding="utf-8")
    (root / "ignored.txt").write_text("ignored", encoding="utf-8")

    documents = MarkdownKnowledgeLoader(root).load_all()

    assert [document.source for document in documents] == [
        "knowledge/a.md",
        "knowledge/nested/b.MD",
        "knowledge/z.md",
    ]


def test_rejects_unsafe_source_on_manually_created_document() -> None:
    document = MarkdownDocument("Content", "../secret.md")

    with pytest.raises(InvalidKnowledgePathError):
        SectionAwareMarkdownChunker().chunk(document)


def test_markdown_inside_code_fence_is_data_not_a_section() -> None:
    document = MarkdownDocument(
        "# Policy\n\n```text\n# Not a heading\n```\n\nAnswer.",
        "knowledge/code.md",
    )

    chunks = SectionAwareMarkdownChunker().chunk(document)

    assert [chunk.section for chunk in chunks] == ["Policy"]
    assert "# Not a heading" in chunks[0].content
