# Migration bổ sung nguồn phân công therapist cho từng reservation.
# Revision: 7f4c2a1b9d10; revision trước: 0e1ac137bdc9.

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f4c2a1b9d10"
down_revision: Union[str, Sequence[str], None] = "0e1ac137bdc9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Thêm assignment_source, backfill từ request type của booking rồi gỡ server default tạm thời.
def upgrade() -> None:
    op.add_column(
        "reservations",
        sa.Column(
            "assignment_source",
            sa.String(length=20),
            nullable=False,
            server_default="auto",
        ),
    )
    op.execute(
        """
        UPDATE reservations AS r
        SET assignment_source = CASE
            WHEN b.therapist_request_type = 'specific' THEN 'specific'
            ELSE 'auto'
        END
        FROM bookings AS b
        WHERE r.booking_id = b.booking_id
        """
    )
    op.alter_column("reservations", "assignment_source", server_default=None)


# Hoàn tác migration bằng cách xóa cột assignment_source khỏi reservations.
def downgrade() -> None:
    op.drop_column("reservations", "assignment_source")
