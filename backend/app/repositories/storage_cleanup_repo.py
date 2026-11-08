from dataclasses import dataclass
from datetime import timedelta
import uuid

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.storage_cleanup import CleanupStatus, StorageCleanupJob


@dataclass(frozen=True)
class CleanupClaim:
    id: uuid.UUID
    document_id: uuid.UUID
    lease_token: uuid.UUID
    attempts: int
    storage_backend: str
    storage_target_identity: str
    storage_bucket_or_root: str
    object_key_or_location: str


class StorageCleanupJobRepository:
    def __init__(self, db: Session):
        self.db = db

    def stage(self, job: StorageCleanupJob) -> None:
        """Join the deletion transaction; its service owns flush and commit."""
        self.db.add(job)

    def claim(self, lease_seconds: int) -> CleanupClaim | None:
        """Stage one claim. Caller commits and closes before any object I/O."""
        clock = func.clock_timestamp()
        job = self.db.scalar(
            select(StorageCleanupJob).where(or_(
                and_(StorageCleanupJob.status.in_([CleanupStatus.PENDING, CleanupStatus.RETRY]),
                     StorageCleanupJob.next_attempt_at <= clock),
                and_(StorageCleanupJob.status == CleanupStatus.PROCESSING,
                     StorageCleanupJob.lease_expires_at <= clock),
            )).order_by(StorageCleanupJob.next_attempt_at, StorageCleanupJob.created_at,
                        StorageCleanupJob.id).limit(1).with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status = CleanupStatus.PROCESSING
        job.lease_token = uuid.uuid4()
        job.lease_expires_at = clock + timedelta(seconds=lease_seconds)
        job.attempts += 1
        job.updated_at = clock
        self.db.flush()
        return CleanupClaim(
            id=job.id, document_id=job.document_id, lease_token=job.lease_token,
            attempts=job.attempts, storage_backend=job.storage_backend,
            storage_target_identity=job.storage_target_identity,
            storage_bucket_or_root=job.storage_bucket_or_root,
            object_key_or_location=job.object_key_or_location,
        )

    def has_s3_reference(self, key: str) -> bool:
        return self.db.scalar(select(Document.id).where(Document.file_path == key).limit(1)) is not None

    def lease_is_current(self, claim: CleanupClaim) -> bool:
        return self.db.scalar(select(StorageCleanupJob.id).where(
            StorageCleanupJob.id == claim.id,
            StorageCleanupJob.status == CleanupStatus.PROCESSING,
            StorageCleanupJob.lease_token == claim.lease_token,
            StorageCleanupJob.lease_expires_at > func.clock_timestamp(),
        )) is not None

    def local_locations(self) -> list[str]:
        return list(self.db.scalars(select(Document.file_path)).all())

    def finish(
        self, claim: CleanupClaim, outcome: CleanupStatus, *, delay: float = 0,
        error_code: str | None = None, error_message: str | None = None,
    ) -> bool:
        """Fence every state transition, including retry/blocked, by the DB clock."""
        if outcome not in {CleanupStatus.DONE, CleanupStatus.RETRY, CleanupStatus.BLOCKED}:
            raise ValueError("Invalid cleanup completion status")
        # Acquire the row before evaluating expiry, without waiting behind a
        # newer claimant. An UPDATE predicate evaluated before a lock wait can
        # otherwise outlive the lease while waiting for that lock.
        locked_id = self.db.scalar(select(StorageCleanupJob.id).where(
            StorageCleanupJob.id == claim.id,
        ).with_for_update(skip_locked=True))
        if locked_id is None:
            return False
        clock = func.clock_timestamp()
        result = self.db.execute(
            update(StorageCleanupJob).where(
                StorageCleanupJob.id == claim.id,
                StorageCleanupJob.status == CleanupStatus.PROCESSING,
                StorageCleanupJob.lease_token == claim.lease_token,
                StorageCleanupJob.lease_expires_at > clock,
            ).values(
                status=outcome, lease_token=None, lease_expires_at=None,
                next_attempt_at=clock + timedelta(seconds=delay), updated_at=clock,
                completed_at=clock if outcome == CleanupStatus.DONE else None,
                last_error_code=error_code, last_error_message=error_message,
            ).execution_options(synchronize_session=False)
        )
        return result.rowcount == 1
