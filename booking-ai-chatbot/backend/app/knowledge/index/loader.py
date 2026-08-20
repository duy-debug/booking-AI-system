"""Đọc Markdown/PDF knowledge document theo cách an toàn."""

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path, PurePosixPath
from typing import Protocol, cast

from app.knowledge.index.errors import (
    InvalidKnowledgeContentError,
    InvalidKnowledgeEncodingError,
    InvalidKnowledgePathError,
    InvalidKnowledgeRootError,
    KnowledgeFileTooLargeError,
    UnsupportedKnowledgeFileError,
)

DEFAULT_MAX_FILE_SIZE = 2 * 1024 * 1024
SUPPORTED_KNOWLEDGE_EXTENSIONS = frozenset({".md", ".pdf"})


class _PdfPage(Protocol):
    # ----------------------------------------------------
    # Contract tối thiểu của một PDF page từ pypdf
    # ----------------------------------------------------
    #
    # Loader chỉ cần extract_text(). Dùng Protocol giúp test fake PDF
    # reader mà không cần import pypdf thật trong unit test.
    # ----------------------------------------------------
    def extract_text(self) -> str | None: ...


class _PdfReader(Protocol):
    # ----------------------------------------------------
    # Contract tối thiểu của PdfReader
    # ----------------------------------------------------
    #
    # pypdf.PdfReader expose pages; mỗi page có thể extract text hoặc
    # trả None nếu PDF là ảnh scan/không có text layer.
    # ----------------------------------------------------
    @property
    def pages(self) -> list[_PdfPage]: ...


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """Chứa knowledge text đã normalize và relative source path an toàn."""

    content: str
    source: str


class MarkdownKnowledgeLoader:
    """Load Markdown/PDF nằm gọn trong một knowledge directory."""

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
            raise InvalidKnowledgeRootError("Knowledge root must be an existing directory.")
        self._root = root
        self._max_file_size = max_file_size

    def load(self, path: Path) -> MarkdownDocument:
        """
        Load một Markdown/PDF file nhưng không cho phép đi ra ngoài root.

        Luồng:

        input path
          -> resolve trong knowledge root
          -> validate file được hỗ trợ
          -> đọc bytes để kiểm tra size
          -> chọn parser theo extension
          -> trả MarkdownDocument
        """

        # ----------------------------------------------------
        # STEP 1: Resolve path tài liệu an toàn
        # ----------------------------------------------------
        #
        # Caller có thể truyền relative path.
        #
        # _resolve_document_path() chuẩn hóa path theo knowledge root
        # đã cấu hình và chặn path traversal.
        # ----------------------------------------------------
        document_path = self._resolve_document_path(path)

        # ----------------------------------------------------
        # STEP 2: Kiểm tra file được hỗ trợ
        # ----------------------------------------------------
        #
        # Ingestion pipeline hiện nhận .md và .pdf.
        #
        # Việc này tránh index nhầm các file local không thuộc knowledge.
        # ----------------------------------------------------
        extension = document_path.suffix.lower()
        if extension not in SUPPORTED_KNOWLEDGE_EXTENSIONS:
            raise UnsupportedKnowledgeFileError(
                "Knowledge loader accepts only Markdown and PDF files."
            )
        if not document_path.is_file():
            raise InvalidKnowledgePathError("Knowledge document must be an existing regular file.")

        # ----------------------------------------------------
        # STEP 3: Chặn file quá lớn trước khi đọc
        # ----------------------------------------------------
        #
        # Document quá lớn có thể tốn memory và làm chậm bước
        # chunking/embedding ngoài dự kiến.
        #
        # Vì vậy cần check size trước khi đưa toàn bộ bytes vào memory.
        # ----------------------------------------------------
        if document_path.stat().st_size > self._max_file_size:
            raise KnowledgeFileTooLargeError(
                "Knowledge document exceeds the configured size limit."
            )

        # ----------------------------------------------------
        # STEP 4: Đọc raw bytes
        # ----------------------------------------------------
        #
        # Lần check size thứ hai bảo vệ trường hợp file thay đổi giữa
        # stat() và read_bytes().
        # ----------------------------------------------------
        raw_content = document_path.read_bytes()
        if len(raw_content) > self._max_file_size:
            raise KnowledgeFileTooLargeError(
                "Knowledge document exceeds the configured size limit."
            )

        # ----------------------------------------------------
        # STEP 5: Chọn parser theo extension
        # ----------------------------------------------------
        #
        # Markdown là plain text UTF-8 nên có thể decode trực tiếp.
        #
        # PDF là binary format nên không dùng rule null byte. Thay vào đó
        # dùng pypdf để extract text layer từ từng page.
        # ----------------------------------------------------
        if extension == ".md":
            content = _decode_markdown(raw_content)
        else:
            content = _extract_pdf_text(document_path)

        # ----------------------------------------------------
        # STEP 6: Chuẩn hóa và trả document
        # ----------------------------------------------------
        #
        # Normalize line ending để chunk ID ổn định trên
        # Windows/macOS/Linux.
        #
        # source là logical path an toàn được lưu trong Qdrant payload.
        # ----------------------------------------------------
        normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
        relative_path = document_path.relative_to(self._root).as_posix()
        source = PurePosixPath(self._root.name, relative_path).as_posix()
        return MarkdownDocument(content=normalized_content, source=source)

    def load_all(self) -> list[MarkdownDocument]:
        """Load toàn bộ Markdown/PDF file theo thứ tự relative path ổn định."""
        # ----------------------------------------------------
        # STEP 1: Tìm toàn bộ knowledge file trong knowledge root
        # ----------------------------------------------------
        #
        # Sort theo relative path để mỗi lần index lại có thứ tự ổn định,
        # giúp test và debug dễ hơn.
        # ----------------------------------------------------
        paths = sorted(
            (
                path
                for path in self._root.rglob("*")
                if path.is_file() and path.suffix.lower() in SUPPORTED_KNOWLEDGE_EXTENSIONS
            ),
            key=lambda path: path.relative_to(self._root).as_posix(),
        )
        # ----------------------------------------------------
        # STEP 2: Đọc từng file bằng cùng rule an toàn
        # ----------------------------------------------------
        #
        # load() vẫn chịu trách nhiệm validate path, size, encoding và
        # tạo MarkdownDocument.
        # ----------------------------------------------------
        return [self.load(path) for path in paths]

    def _resolve_document_path(self, path: Path) -> Path:
        # ----------------------------------------------------
        # STEP 1: Resolve path theo knowledge root
        # ----------------------------------------------------
        #
        # Relative path được nối với root; absolute path được giữ nguyên
        # rồi resolve để loại bỏ các đoạn như "." hoặc "..".
        # ----------------------------------------------------
        candidate = path if path.is_absolute() else self._root / path
        resolved = candidate.resolve()

        # ----------------------------------------------------
        # STEP 2: Chặn path traversal
        # ----------------------------------------------------
        #
        # File hợp lệ bắt buộc phải nằm bên trong knowledge root sau khi
        # resolve, kể cả khi caller cố truyền "../".
        # ----------------------------------------------------
        if not resolved.is_relative_to(self._root):
            raise InvalidKnowledgePathError(
                "Knowledge document must remain inside the configured root."
            )
        return resolved


def _decode_markdown(raw_content: bytes) -> str:
    # ----------------------------------------------------
    # STEP 1: Chặn Markdown binary
    # ----------------------------------------------------
    #
    # Markdown phải là text. Null byte là tín hiệu đơn giản cho thấy file
    # có thể là binary hoặc bị lỗi với pipeline này.
    # ----------------------------------------------------
    if b"\x00" in raw_content:
        raise InvalidKnowledgeContentError(
            "Knowledge document must contain text rather than binary data."
        )

    # ----------------------------------------------------
    # STEP 2: Decode UTF-8
    # ----------------------------------------------------
    #
    # Các bước RAG phía sau làm việc với Python string đã normalize,
    # không làm việc trực tiếp với bytes.
    # ----------------------------------------------------
    try:
        return raw_content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InvalidKnowledgeEncodingError(
            "Knowledge document must use UTF-8 encoding."
        ) from error


def _extract_pdf_text(path: Path) -> str:
    # ----------------------------------------------------
    # STEP 1: Import pypdf khi thật sự cần
    # ----------------------------------------------------
    #
    # Nếu project chỉ index Markdown thì không cần load pypdf. Khi gặp PDF,
    # loader mới import parser PDF.
    # ----------------------------------------------------
    try:
        pdf_module = import_module("pypdf")
    except ImportError as error:
        raise UnsupportedKnowledgeFileError(
            "PDF knowledge loading requires the pypdf package."
        ) from error
    pdf_reader = pdf_module.PdfReader

    # ----------------------------------------------------
    # STEP 2: Extract text từ từng page
    # ----------------------------------------------------
    #
    # PDF export từ Word/browser thường có text layer. PDF scan ảnh có thể
    # trả text rỗng, khi đó loader reject để tránh index document trống.
    # ----------------------------------------------------
    reader = cast(_PdfReader, pdf_reader(path))
    pages: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text and page_text.strip():
            pages.append(page_text.strip())

    # ----------------------------------------------------
    # STEP 3: Ghép page text thành một document
    # ----------------------------------------------------
    #
    # Dùng hai dòng trống để giữ ranh giới page tương tự paragraph break,
    # giúp chunker phía sau tách nội dung tự nhiên hơn.
    # ----------------------------------------------------
    content = "\n\n".join(pages)
    if not content.strip():
        raise InvalidKnowledgeContentError(
            "PDF knowledge document contains no extractable text."
        )
    return content
