"""Đọc Markdown knowledge document theo cách an toàn."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.knowledge.index.errors import (
    InvalidKnowledgeContentError,
    InvalidKnowledgeEncodingError,
    InvalidKnowledgePathError,
    InvalidKnowledgeRootError,
    KnowledgeFileTooLargeError,
    UnsupportedKnowledgeFileError,
)

DEFAULT_MAX_FILE_SIZE = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class MarkdownDocument:
    """Chứa Markdown text đã normalize và relative source path an toàn."""

    content: str
    source: str


class MarkdownKnowledgeLoader:
    """Load Markdown UTF-8 nằm gọn trong một knowledge directory."""

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
        Load một Markdown file nhưng không cho phép đi ra ngoài root.

        Luồng:

        input path
          -> resolve trong knowledge root
          -> validate Markdown file
          -> đọc bytes
          -> decode UTF-8 text
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
        # STEP 2: Kiểm tra Markdown file
        # ----------------------------------------------------
        #
        # Ingestion pipeline chỉ nhận file .md thật.
        #
        # Việc này tránh index nhầm các file local không thuộc knowledge.
        # ----------------------------------------------------
        if document_path.suffix.lower() != ".md":
            raise UnsupportedKnowledgeFileError("Knowledge loader accepts only Markdown files.")
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
        # STEP 5: Chặn nội dung binary
        # ----------------------------------------------------
        #
        # Knowledge Markdown phải là text.
        #
        # Null byte là tín hiệu đơn giản cho thấy file có thể là binary
        # hoặc bị lỗi với pipeline này.
        # ----------------------------------------------------
        if b"\x00" in raw_content:
            raise InvalidKnowledgeContentError(
                "Knowledge document must contain text rather than binary data."
            )

        # ----------------------------------------------------
        # STEP 6: Decode UTF-8
        # ----------------------------------------------------
        #
        # Các bước RAG phía sau làm việc với Python string đã normalize,
        # không làm việc trực tiếp với bytes.
        # ----------------------------------------------------
        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InvalidKnowledgeEncodingError(
                "Knowledge document must use UTF-8 encoding."
            ) from error

        # ----------------------------------------------------
        # STEP 7: Chuẩn hóa và trả document
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
        """Load toàn bộ Markdown file theo thứ tự relative path ổn định."""
        # ----------------------------------------------------
        # STEP 1: Tìm toàn bộ Markdown file trong knowledge root
        # ----------------------------------------------------
        #
        # Sort theo relative path để mỗi lần index lại có thứ tự ổn định,
        # giúp test và debug dễ hơn.
        # ----------------------------------------------------
        paths = sorted(
            (
                path
                for path in self._root.rglob("*")
                if path.is_file() and path.suffix.lower() == ".md"
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
