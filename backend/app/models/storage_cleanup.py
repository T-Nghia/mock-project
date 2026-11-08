"""Durable deletion intent, independent of the document and requesting user."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CleanupStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRY = "retry"
    BLOCKED = "blocked"
    DONE = "done"


class StorageCleanupJob(Base):
    __tablename__ = "storage_cleanup_jobs"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_storage_cleanup_attempts"),
        Index(
            "ix_storage_cleanup_due", "next_attempt_at", "created_at",
            postgresql_where=text("status IN ('pending', 'retry')"),
        ),
        Index(
            "ix_storage_cleanup_expired_lease", "lease_expires_at",
            postgresql_where=text("status = 'processing'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Snapshots intentionally have no FK: hard deletion must never remove intent.
    document_id: Mapped[uuid.UUID] = mapped_column(unique=True, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_target_identity: Mapped[str] = mapped_column(Text, nullable=False)
    storage_bucket_or_root: Mapped[str] = mapped_column(Text, nullable=False)
    object_key_or_location: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CleanupStatus] = mapped_column(
        Enum(
            CleanupStatus, values_callable=lambda statuses: [state.value for state in statuses],
            native_enum=False, create_constraint=True, name="storagecleanupstatus",
        ),
        nullable=False, default=CleanupStatus.PENDING, server_default="pending",
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        # Let PostgreSQL schedule initial work too; API clock skew must not
        # postpone a committed deletion. The M1 server default already exists.
        server_default=text("CURRENT_TIMESTAMP"),
    )
    lease_token: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default=text("CURRENT_TIMESTAMP"),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
