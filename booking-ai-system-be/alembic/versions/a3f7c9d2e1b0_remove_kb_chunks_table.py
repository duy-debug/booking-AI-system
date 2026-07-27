"""Remove the legacy PostgreSQL RAG table.

RAG data is owned by the standalone chatbot and stored in Qdrant. The vector
extension is intentionally retained because it may be shared by other schemas
or applications using the same PostgreSQL database.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a3f7c9d2e1b0"
down_revision: Union[str, Sequence[str], None] = "a8c4e2f19b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kb_chunks")


def downgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
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
