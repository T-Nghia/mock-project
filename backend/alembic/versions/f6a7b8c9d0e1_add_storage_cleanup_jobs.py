"""add durable storage cleanup queue

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_cleanup_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("storage_backend", sa.String(20), nullable=False),
        sa.Column("storage_target_identity", sa.Text(), nullable=False),
        sa.Column("storage_bucket_or_root", sa.Text(), nullable=False),
        sa.Column("object_key_or_location", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum(
            "pending", "processing", "retry", "blocked", "done",
            name="storagecleanupstatus", native_enum=False, create_constraint=True,
        ), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id"),
        sa.CheckConstraint("attempts >= 0", name="ck_storage_cleanup_attempts"),
    )
    op.create_index(
        "ix_storage_cleanup_due", "storage_cleanup_jobs", ["next_attempt_at", "created_at"],
        postgresql_where=sa.text("status IN ('pending', 'retry')"),
    )
    op.create_index(
        "ix_storage_cleanup_expired_lease", "storage_cleanup_jobs", ["lease_expires_at"],
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade() -> None:
    # Unfinished intent must never be silently discarded by a rollback.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM storage_cleanup_jobs)")):
        raise RuntimeError("Refusing to drop a nonempty storage cleanup queue")
    op.drop_table("storage_cleanup_jobs")
