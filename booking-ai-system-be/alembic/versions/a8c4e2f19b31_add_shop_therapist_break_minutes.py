# Thêm cấu hình thời gian nghỉ giữa hai booking theo shop.

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8c4e2f19b31"
down_revision: Union[str, Sequence[str], None] = "7f4c2a1b9d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Thêm cấu hình nghỉ với mặc định 0 để giữ nguyên hành vi của dữ liệu hiện tại.
def upgrade() -> None:
    op.add_column(
        "shops",
        sa.Column(
            "therapist_break_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_shops_therapist_break_minutes",
        "shops",
        "therapist_break_minutes IN (0, 5, 10, 15)",
    )
    op.alter_column("shops", "therapist_break_minutes", server_default=None)


# Gỡ constraint trước khi xóa cột cấu hình nghỉ.
def downgrade() -> None:
    op.drop_constraint(
        "ck_shops_therapist_break_minutes",
        "shops",
        type_="check",
    )
    op.drop_column("shops", "therapist_break_minutes")
