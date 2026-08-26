"""Add customer FK to customer restrictions.

Revision ID: b6a3f8c9d2e4
Revises: a3f7c9d2e1b0
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b6a3f8c9d2e4"
down_revision: str | Sequence[str] | None = "a3f7c9d2e1b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customer_restrictions",
        sa.Column("customer_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_customer_restrictions_customer_id"),
        "customer_restrictions",
        ["customer_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_customer_restrictions_customer_id_customers",
        "customer_restrictions",
        "customers",
        ["customer_id"],
        ["customer_id"],
    )
    op.execute(
        """
        UPDATE customer_restrictions AS cr
        SET customer_id = c.customer_id
        FROM customers AS c
        WHERE cr.customer_id IS NULL
          AND cr.phone = c.phone
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_customer_restrictions_customer_id_customers",
        "customer_restrictions",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_customer_restrictions_customer_id"),
        table_name="customer_restrictions",
    )
    op.drop_column("customer_restrictions", "customer_id")
