"""Load and section-aware chunk trusted Markdown knowledge documents."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DEFAULT_MAX_CHUNK_SIZE = 1_000
DEFAULT_MAX_FILE_SIZE = 2 * 1024 * 1024

_ATX_HEADING_PATTERN = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")
_PARAGRAPH_BREAK_PATTERN = re.compile(r"\n[ \t]*\n+")


class KnowledgeIngestionError(Exception):
    """Base error for offline knowledge-document ingestion failures."""


class InvalidKnowledgeRootError(KnowledgeIngestionError):
    """Raised when the configured knowledge root is not a readable directory."""


class InvalidKnowledgePathError(KnowledgeIngestionError):
    """Raised when a document path escapes the configured knowledge root."""


class UnsupportedKnowledgeFileError(KnowledgeIngestionError):
    """Raised when a requested knowledge document is not a Markdown file."""


class KnowledgeFileTooLargeError(KnowledgeIngestionError):
    """Raised when a knowledge document exceeds the configured size limit."""


class InvalidKnowledgeEncodingError(KnowledgeIngestionError):
    """Raised when a knowledge document is not valid UTF-8 text."""


class InvalidKnowledgeContentError(KnowledgeIngestionError):
    """Raised when a knowledge document contains unsupported binary content."""


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """Contains normalized Markdown text and its safe relative source path."""

    content: str
    source: str


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """Represents one deterministic, embedding-ready knowledge text chunk."""

    chunk_id: str
    content: str
    source: str
    section: str | None
    chunk_index: int


@dataclass(frozen=True, slots=True)
class _MarkdownSection:
    heading: str | None
    body: str


class MarkdownKnowledgeLoader:
    """Load UTF-8 Markdown documents confined to one knowledge directory."""

    def __init__(
        self,
        knowledge_root: Path,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        if type(max_file_size) is not int or max_file_size <= 0:
            raise ValueError("Knowledge file size limit must be a positive integer.")
        root = knowledge_root.resolve()
        if not root.is_dir():
            raise InvalidKnowledgeRootError(
                "Knowledge root must be an existing directory."
            )
        self._root = root
        self._max_file_size = max_file_size

    def load(self, path: Path) -> MarkdownDocument:
        """Load one Markdown file without allowing access outside the root."""
        document_path = self._resolve_document_path(path)
        if document_path.suffix.lower() != ".md":
            raise UnsupportedKnowledgeFileError(
                "Knowledge loader accepts only Markdown files."
            )
        if not document_path.is_file():
            raise InvalidKnowledgePathError(
                "Knowledge document must be an existing regular file."
            )
        if document_path.stat().st_size > self._max_file_size:
            raise KnowledgeFileTooLargeError(
                "Knowledge document exceeds the configured size limit."
            )
        raw_content = document_path.read_bytes()
        if len(raw_content) > self._max_file_size:
            raise KnowledgeFileTooLargeError(
                "Knowledge document exceeds the configured size limit."
            )
        if b"\x00" in raw_content:
            raise InvalidKnowledgeContentError(
                "Knowledge document must contain text rather than binary data."
            )
        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InvalidKnowledgeEncodingError(
                "Knowledge document must use UTF-8 encoding."
            ) from error
        normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
        relative_path = document_path.relative_to(self._root).as_posix()
        source = PurePosixPath(self._root.name, relative_path).as_posix()
        return MarkdownDocument(content=normalized_content, source=source)

    def load_all(self) -> list[MarkdownDocument]:
        """Load all Markdown files in deterministic relative-path order."""
        paths = sorted(
            (
                path
                for path in self._root.rglob("*")
                if path.is_file() and path.suffix.lower() == ".md"
            ),
            key=lambda path: path.relative_to(self._root).as_posix(),
        )
        return [self.load(path) for path in paths]

    def _resolve_document_path(self, path: Path) -> Path:
        candidate = path if path.is_absolute() else self._root / path
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self._root):
            raise InvalidKnowledgePathError(
                "Knowledge document must remain inside the configured root."
            )
        return resolved


class SectionAwareMarkdownChunker:
    """Split Markdown by headings, paragraphs, and finally bounded word groups."""

    def __init__(self, *, max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE) -> None:
        if type(max_chunk_size) is not int or max_chunk_size < 64:
            raise ValueError("Maximum chunk size must be an integer of at least 64.")
        self._max_chunk_size = max_chunk_size

    def chunk(self, document: MarkdownDocument) -> list[KnowledgeChunk]:
        """Create ordered chunks for one normalized Markdown document."""
        _validate_source(document.source)
        chunks: list[KnowledgeChunk] = []
        for section in _extract_sections(document.content):
            prefix = f"# {section.heading}\n\n" if section.heading else ""
            available_size = self._max_chunk_size - len(prefix)
            if available_size < 1:
                raise InvalidKnowledgeContentError(
                    "Markdown heading leaves no room for section content."
                )
            for body in _split_section_body(section.body, available_size):
                content = f"{prefix}{body}" if prefix else body
                chunk_index = len(chunks)
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=_chunk_id(
                            source=document.source,
                            section=section.heading,
                            chunk_index=chunk_index,
                            content=content,
                        ),
                        content=content,
                        source=document.source,
                        section=section.heading,
                        chunk_index=chunk_index,
                    )
                )
        return chunks

    def chunk_all(
        self,
        documents: list[MarkdownDocument],
    ) -> list[KnowledgeChunk]:
        """Chunk documents in their supplied deterministic order."""
        return [chunk for document in documents for chunk in self.chunk(document)]


def _extract_sections(content: str) -> tuple[_MarkdownSection, ...]:
    sections: list[_MarkdownSection] = []
    heading: str | None = None
    body_lines: list[str] = []
    fence_marker: str | None = None

    def append_section() -> None:
        body = "\n".join(body_lines).strip()
        if body:
            sections.append(_MarkdownSection(heading=heading, body=body))

    for line in content.split("\n"):
        stripped = line.lstrip()
        current_fence = _fence_marker(stripped)
        if current_fence is not None:
            if fence_marker is None:
                fence_marker = current_fence
            elif current_fence == fence_marker:
                fence_marker = None
            body_lines.append(line)
            continue
        match = _ATX_HEADING_PATTERN.fullmatch(line)
        if match is not None and fence_marker is None:
            append_section()
            heading = match.group(1).strip()
            body_lines = []
            continue
        body_lines.append(line)
    append_section()
    return tuple(sections)


def _fence_marker(line: str) -> str | None:
    if line.startswith("```"):
        return "`"
    if line.startswith("~~~"):
        return "~"
    return None


def _split_section_body(body: str, max_size: int) -> tuple[str, ...]:
    paragraphs = tuple(
        normalized
        for paragraph in _PARAGRAPH_BREAK_PATTERN.split(body)
        if (normalized := _normalize_paragraph(paragraph))
    )
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_paragraph(paragraph, max_size))
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_size:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return tuple(chunks)


def _normalize_paragraph(paragraph: str) -> str:
    return "\n".join(line.rstrip() for line in paragraph.strip().split("\n")).strip()


def _split_long_paragraph(paragraph: str, max_size: int) -> tuple[str, ...]:
    words = paragraph.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(word) <= max_size:
                current = word
            else:
                chunks.extend(
                    word[index : index + max_size]
                    for index in range(0, len(word), max_size)
                )
                current = ""
    if current:
        chunks.append(current)
    return tuple(chunks)


def _chunk_id(
    *,
    source: str,
    section: str | None,
    chunk_index: int,
    content: str,
) -> str:
    identity = "\x00".join((source, section or "", str(chunk_index), content))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"kc_{digest[:24]}"


def _validate_source(source: str) -> None:
    path = PurePosixPath(source)
    if (
        not source
        or path.is_absolute()
        or "\\" in source
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise InvalidKnowledgePathError(
            "Knowledge source must be a safe relative POSIX path."
        )
