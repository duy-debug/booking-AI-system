"""Các loại lỗi dùng cho ingestion và indexing knowledge offline."""


class KnowledgeIngestionError(Exception):
    """Lỗi gốc cho các lỗi đọc/chuẩn hóa knowledge document offline."""


class InvalidKnowledgeRootError(KnowledgeIngestionError):
    """Được raise khi knowledge root không phải thư mục đọc được."""


class InvalidKnowledgePathError(KnowledgeIngestionError):
    """Được raise khi document path đi ra ngoài knowledge root."""


class UnsupportedKnowledgeFileError(KnowledgeIngestionError):
    """Được raise khi document không phải Markdown file."""


class KnowledgeFileTooLargeError(KnowledgeIngestionError):
    """Được raise khi document vượt giới hạn dung lượng cấu hình."""


class InvalidKnowledgeEncodingError(KnowledgeIngestionError):
    """Được raise khi document không phải UTF-8 text hợp lệ."""


class InvalidKnowledgeContentError(KnowledgeIngestionError):
    """Được raise khi document chứa binary content không hỗ trợ."""


class KnowledgeIndexingError(Exception):
    """Lỗi gốc cho các lỗi indexing knowledge đã dự đoán được."""


class InvalidIndexingSourceError(KnowledgeIndexingError):
    """Được raise khi source cần index không phải Markdown file tồn tại."""


class EmptyKnowledgeDocumentError(KnowledgeIndexingError):
    """Được raise khi ingestion không tạo được chunk có thể index."""


class IncompatibleCollectionError(KnowledgeIndexingError):
    """Được raise khi collection cũ có cấu hình vector không tương thích."""
