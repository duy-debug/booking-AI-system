from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class CustomerRestriction(TimestampMixin, Base):
    # NG list - danh sach khach hang bi han che dat booking.
    __tablename__ = "customer_restrictions"

    # Giu unique active theo phone de cac flow cu va API hien tai khong bi vo.
    __table_args__ = (
        Index(
            "idx_active_restriction_phone",
            "phone",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    restriction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.customer_id"),
        nullable=True,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    customer = relationship("Customer", back_populates="restrictions")

    def __repr__(self) -> str:
        return f"<Restriction {self.phone} active={self.is_active}>"
