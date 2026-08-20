"""Section-aware chunking for Markdown knowledge documents."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

# Các lỗi/path model từ loader được dùng lại để chunker giữ cùng rule an toàn
# với bước ingestion: source phải là logical path an toàn, content phải hợp lệ.
from app.knowledge.index.loader import (
    InvalidKnowledgeContentError,
    InvalidKnowledgePathError,
    MarkdownDocument,
)

# Giới hạn mặc định cho mỗi chunk trước khi embed.
#
# Giá trị này giữ chunk đủ nhỏ để embedding ổn định, nhưng vẫn đủ context cho
# retrieval trả lời FAQ.
DEFAULT_MAX_CHUNK_SIZE = 1_000

# ATX heading là dạng heading Markdown dùng dấu "#".
#
# Regex này lấy text heading và bỏ dấu "#" thừa ở cuối nếu có.
_ATX_HEADING_PATTERN = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")

# Paragraph break là một hoặc nhiều dòng trống.
#
# Chunker ưu tiên tách theo paragraph trước khi phải tách sâu hơn theo word.
_PARAGRAPH_BREAK_PATTERN = re.compile(r"\n[ \t]*\n+")


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """Một knowledge text chunk ổn định và sẵn sàng để embed."""

    # ID deterministic của chunk, dùng để tạo Qdrant point id ổn định.
    chunk_id: str

    # Nội dung text thật sẽ được đưa vào embedding model.
    content: str

    # Logical source path an toàn, lưu vào Qdrant payload để trace nguồn.
    source: str

    # Heading Markdown gần nhất, giúp retrieval giữ được ngữ cảnh section.
    section: str | None

    # Vị trí chunk trong document gốc, dùng để giữ thứ tự đọc/debug.
    chunk_index: int


@dataclass(frozen=True, slots=True)
class _MarkdownSection:
    # Heading hiện tại của section; None nếu document có content trước heading.
    heading: str | None

    # Body text thuộc section đó, chưa được tách thành chunk nhỏ.
    body: str


class SectionAwareMarkdownChunker:
    """Tách Markdown theo heading, paragraph và nhóm từ có giới hạn."""

    def __init__(self, *, max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE) -> None:
        if type(max_chunk_size) is not int or max_chunk_size < 64:
            raise ValueError("Maximum chunk size must be an integer of at least 64.")
        self._max_chunk_size = max_chunk_size

    def chunk(self, document: MarkdownDocument) -> list[KnowledgeChunk]:
        """
        Tạo danh sách chunk có thứ tự cho một Markdown document đã normalize.

        Luồng:

        MarkdownDocument
          -> validate logical source
          -> tách theo heading
          -> tách section body lớn
          -> tạo danh sách KnowledgeChunk deterministic
        """

        # ----------------------------------------------------
        # STEP 1: Kiểm tra logical source
        # ----------------------------------------------------
        #
        # source sẽ được lưu vào Qdrant payload.
        #
        # Vì vậy nó phải là relative POSIX-like path để response không
        # leak local filesystem path.
        # ----------------------------------------------------
        _validate_source(document.source)
        chunks: list[KnowledgeChunk] = []

        # ----------------------------------------------------
        # STEP 2: Tách Markdown thành section
        # ----------------------------------------------------
        #
        # Heading sẽ trở thành metadata section.
        #
        # Heading cũng được giữ làm prefix trong chunk content để
        # retrieval có thêm ngữ cảnh của section.
        # ----------------------------------------------------
        for section in _extract_sections(document.content):
            prefix = f"# {section.heading}\n\n" if section.heading else ""
            available_size = self._max_chunk_size - len(prefix)
            if available_size < 1:
                raise InvalidKnowledgeContentError(
                    "Markdown heading leaves no room for section content."
                )

            # ------------------------------------------------
            # STEP 3: Tách section body
            # ------------------------------------------------
            #
            # Section dài được tách theo paragraph trước, sau đó mới
            # tách theo word nếu paragraph vẫn vượt max size.
            # ------------------------------------------------
            for body in _split_section_body(section.body, available_size):
                content = f"{prefix}{body}" if prefix else body
                chunk_index = len(chunks)

                # --------------------------------------------
                # STEP 4: Tạo chunk deterministic
                # --------------------------------------------
                #
                # chunk_id được sinh từ source, section, index và content.
                #
                # Re-index cùng một nội dung sẽ tạo lại cùng một identity.
                # --------------------------------------------
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

        # ----------------------------------------------------
        # STEP 5: Trả chunk đúng thứ tự
        # ----------------------------------------------------
        #
        # chunk_index giữ đúng thứ tự xuất hiện trong document gốc.
        # ----------------------------------------------------
        return chunks

    def chunk_all(self, documents: list[MarkdownDocument]) -> list[KnowledgeChunk]:
        """Chunk documents in their supplied deterministic order."""
        # ----------------------------------------------------
        # STEP 1: Chunk nhiều document theo đúng thứ tự đầu vào
        # ----------------------------------------------------
        #
        # Hàm này chỉ flatten kết quả, còn rule tách chunk vẫn nằm trong
        # chunk() để tránh hai luồng xử lý khác nhau.
        # ----------------------------------------------------
        return [chunk for document in documents for chunk in self.chunk(document)]


def _extract_sections(content: str) -> tuple[_MarkdownSection, ...]:
    # ----------------------------------------------------
    # STEP 1: Duyệt Markdown và gom nội dung theo ATX heading
    # ----------------------------------------------------
    #
    # Heading trong code fence bị bỏ qua để không tách nhầm nội dung code.
    # ----------------------------------------------------
    sections: list[_MarkdownSection] = []
    heading: str | None = None
    body_lines: list[str] = []
    in_code_fence = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
        if not in_code_fence and (match := _ATX_HEADING_PATTERN.match(line)) is not None:
            _append_section(sections, heading, body_lines)
            heading = match.group(1).strip()
            body_lines = []
            continue
        body_lines.append(line)
    _append_section(sections, heading, body_lines)
    return tuple(sections)


def _append_section(
    sections: list[_MarkdownSection],
    heading: str | None,
    body_lines: list[str],
) -> None:
    # ----------------------------------------------------
    # STEP 1: Chỉ thêm section có body thật
    # ----------------------------------------------------
    #
    # Heading rỗng hoặc đoạn trắng không tạo chunk để tránh noise khi embed.
    # ----------------------------------------------------
    body = "\n".join(body_lines).strip()
    if body:
        sections.append(_MarkdownSection(heading=heading, body=body))


def _split_section_body(body: str, max_size: int) -> tuple[str, ...]:
    # ----------------------------------------------------
    # STEP 1: Ưu tiên tách theo paragraph
    # ----------------------------------------------------
    #
    # Paragraph giữ ngữ nghĩa tốt hơn word split, nên ta chỉ tách sâu hơn
    # khi paragraph vượt quá max_size.
    # ----------------------------------------------------
    paragraphs = [
        paragraph.strip()
        for paragraph in _PARAGRAPH_BREAK_PATTERN.split(body)
        if paragraph.strip()
    ]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [body.strip()]:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(paragraph) <= max_size:
            current = paragraph
            continue
        chunks.extend(_split_paragraph(paragraph, max_size))
    if current:
        chunks.append(current)
    return tuple(chunks)


def _split_paragraph(paragraph: str, max_size: int) -> tuple[str, ...]:
    # ----------------------------------------------------
    # STEP 1: Tách paragraph theo word
    # ----------------------------------------------------
    #
    # Nếu một word đơn lẻ vẫn quá dài, cắt theo ký tự để đảm bảo không có
    # chunk nào vượt max_size.
    # ----------------------------------------------------
    words = paragraph.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(word) <= max_size:
            current = word
            continue
        chunks.extend(
            word[index : index + max_size] for index in range(0, len(word), max_size)
        )
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
    # ----------------------------------------------------
    # STEP 1: Sinh chunk_id ổn định từ nội dung chunk
    # ----------------------------------------------------
    #
    # source + section + chunk_index + content tạo thành identity. Hash
    # giúp ID ngắn, ổn định và không chứa path/text thô.
    # ----------------------------------------------------
    identity = "\x00".join((source, section or "", str(chunk_index), content))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"kc_{digest[:24]}"


def _validate_source(source: str) -> None:
    # ----------------------------------------------------
    # STEP 1: Kiểm tra source là logical POSIX path an toàn
    # ----------------------------------------------------
    #
    # Không cho absolute path, backslash, "." hoặc ".." để tránh leak
    # filesystem path và tránh metadata source không nhất quán.
    # ----------------------------------------------------
    path = PurePosixPath(source)
    if (
        not source
        or path.is_absolute()
        or "\\" in source
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise InvalidKnowledgePathError("Knowledge source must be a safe relative POSIX path.")
