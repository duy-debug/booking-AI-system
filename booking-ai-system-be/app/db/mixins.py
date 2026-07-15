# Mixin chứa các trường thời gian dùng chung cho tất cả model
# Giúp tránh lặp code created_at / updated_at

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    # Thời điểm tạo bản ghi — do database tự gán (server_default)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Thời điểm cập nhật gần nhất — tự động cập nhật khi record thay đổi
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
