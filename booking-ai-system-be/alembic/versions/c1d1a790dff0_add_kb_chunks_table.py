# Migration tạo bảng kb_chunks và kích hoạt extension pgvector.
# Revision: c1d1a790dff0; revision trước: dee2e56ef8bf.
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c1d1a790dff0'
down_revision: Union[str, Sequence[str], None] = 'dee2e56ef8bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tạo extension vector, bảng knowledge chunks và index tìm kiếm theo source.
def upgrade() -> None:
    # Kích hoạt extension pgvector (nếu chưa có)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Dùng SQL thuần để migration lịch sử vẫn chạy được mà Booking Backend
    # không phải giữ dependency pgvector chỉ cho một bảng RAG đã ngừng sử dụng.
    op.execute(
        """
        CREATE TABLE kb_chunks (
            chunk_id UUID NOT NULL PRIMARY KEY,
            source VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR(384),
            chunk_order INTEGER,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_kb_chunks_source ON kb_chunks (source)")


# Xóa index và bảng kb_chunks để quay lại schema trước migration.
def downgrade() -> None:
    op.execute("DROP INDEX ix_kb_chunks_source")
    op.execute("DROP TABLE kb_chunks")
