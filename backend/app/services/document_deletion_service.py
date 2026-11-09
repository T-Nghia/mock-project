"""Atomically hard-delete metadata and persist physical cleanup intent."""

import logging
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import uuid

from fastapi import HTTPException, status
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, SessionTransactionOrigin

from app.core.config import settings
from app.models.storage_cleanup import StorageCleanupJob
from app.models.user import User, UserRole
from app.repositories.document_repo import DocumentRepository
from app.repositories.storage_cleanup_repo import StorageCleanupJobRepository

logger = logging.getLogger(__name__)


def snapshot_storage_locator(location: str) -> dict[str, str]:
    """Snapshot configuration without accessing storage or copying credentials.

    Existing uploads store a local path or an S3 object key, never a signed URL.
    Local workers must later use the same filesystem mount as the API.
    """
    backend = settings.STORAGE_BACKEND.lower()
    if backend == "local":
        root = Path(settings.UPLOAD_DIR).resolve()
        path = Path(location).resolve()
        try:
            key = path.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("Document location is outside the configured storage root") from exc
        if path == root:
            raise RuntimeError("Document location must identify an object")
        return {
            "storage_backend": "local",
            "storage_target_identity": f"local:{root}",
            "storage_bucket_or_root": str(root),
            "object_key_or_location": key.as_posix(),
        }
    if backend == "s3":
        if not settings.STORAGE_BUCKET or not location:
            raise RuntimeError("S3 cleanup requires a bucket and object key")
        endpoint = settings.STORAGE_ENDPOINT_URL
        if endpoint:
            parsed = urlsplit(endpoint)
            if (
                parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment
            ):
                raise RuntimeError("S3 cleanup requires a credential-free endpoint URL")
            # Validate the port too; malformed configuration must not delete metadata.
            parsed.port
            target = urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, "", ""))
        else:
            target = f"aws:s3:{settings.STORAGE_REGION}"
        if urlsplit(location).scheme or location.startswith("//"):
            raise RuntimeError("S3 cleanup requires an object key, not a URL")
        return {
            "storage_backend": "s3",
            "storage_target_identity": target,
            "storage_bucket_or_root": settings.STORAGE_BUCKET,
            "object_key_or_location": location,
        }
    raise RuntimeError("Unsupported storage backend for durable cleanup")


class DocumentDeletionService:
    def __init__(self, db: Session):
        self.db = db
        self.documents = DocumentRepository(db)
        self.jobs = StorageCleanupJobRepository(db)

    def _validate_request_session(self) -> None:
        """Accept the read-only auth autobegin, never commit another unit of work."""
        transaction = self.db.get_transaction()
        if (
            self.db.autoflush or not self.db.is_active or self.db.in_nested_transaction()
            or self.db.new or self.db.dirty or self.db.deleted
            or (transaction is not None and transaction.origin != SessionTransactionOrigin.AUTOBEGIN)
        ):
            raise RuntimeError("Deletion requires a clean request session with autoflush disabled")
        bind = self.db.get_bind()
        if isinstance(bind, Connection) and bind.in_transaction():
            raise RuntimeError("Deletion cannot confirm a commit owned by an external transaction")

    def delete_document(self, document_id: uuid.UUID, current_user: User) -> None:
        self._validate_request_session()
        # Capture auth data before any rollback/commit can expire ORM attributes.
        actor_id, actor_role = current_user.id, current_user.role
        try:
            document = self.documents.get_for_update(document_id)
            if document is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài liệu.")
            if document.uploaded_by != actor_id and actor_role != UserRole.ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Bạn chỉ có thể xóa tài liệu do chính mình tải lên.",
                )
            locator = snapshot_storage_locator(document.file_path)
            self.jobs.stage(StorageCleanupJob(
                document_id=document.id, requested_by=actor_id, **locator,
            ))
            self.documents.stage_delete(document)
            self.db.flush()
        except Exception:
            self.db.rollback()
            raise

        try:
            self.db.commit()
        except Exception:
            # A lost COMMIT acknowledgement can mean it committed. Reset the
            # session, propagate failure, and never claim the deletion rolled back.
            logger.error("Document deletion commit was not confirmed; outcome may be unknown")
            self.db.rollback()
            raise
