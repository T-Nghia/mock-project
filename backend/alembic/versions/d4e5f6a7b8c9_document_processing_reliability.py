"""add document processing reliability metadata

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("processing_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("documents", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("processing_last_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("processing_task_id", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_document_chunk_index", "document_chunks", ["document_id", "chunk_index"])


def downgrade() -> None:
    op.drop_constraint("uq_document_chunk_index", "document_chunks", type_="unique")
    op.drop_column("documents", "processing_task_id")
    op.drop_column("documents", "processing_last_error")
    op.drop_column("documents", "processing_completed_at")
    op.drop_column("documents", "processing_started_at")
    op.drop_column("documents", "processing_attempts")
