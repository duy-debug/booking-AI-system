# Model lưu text chunks đã embed — dùng cho RAG (vector search)
# Mỗi chunk là một đoạn nhỏ từ tài liệu business/docs, được nhúng vector 384 chiều

import uuid

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class KnowledgeChunk(Base):
    __tablename__ = "kb_chunks"

    chunk_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Tên file nguồn (ví dụ: define_uc_ut_processflow.md)
    source = Column(String(255), nullable=False, index=True)
    # Nội dung text của chunk
    content = Column(Text, nullable=False)
    # Vector embedding 384 chiều (all-MiniLM-L6-v2)
    embedding = Column(Vector(384), nullable=True)
    # Thứ tự chunk trong file
    chunk_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Tạo chuỗi đại diện rút gọn cho đoạn tri thức để thuận tiện theo dõi khi debug.
    def __repr__(self):
        return f"<KnowledgeChunk {self.source} #{self.chunk_order}>"
