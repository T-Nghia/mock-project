"""Bounded queue metrics index and transactional operator audit.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_storage_cleanup_status_created", "storage_cleanup_jobs", ["status", "created_at"])
    op.create_table(
        "storage_cleanup_requeues",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("storage_cleanup_jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=False),
        sa.Column("operator", sa.String(100), nullable=False),
        sa.Column("ticket", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    # Never discard operator history during an automatic rollback.
    raise RuntimeError("Cleanup operations downgrade requires an audited forward migration; retain queue and audit")
