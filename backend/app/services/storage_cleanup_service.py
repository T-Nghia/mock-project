"""At-least-once physical cleanup, driven only by PostgreSQL state."""

from dataclasses import dataclass
import errno
import logging
from pathlib import Path
import random
from typing import Callable

from botocore.exceptions import (
    ClientError, ConnectionClosedError, ConnectTimeoutError, EndpointConnectionError, ProxyConnectionError,
    ReadTimeoutError,
)
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.models.storage_cleanup import CleanupStatus
from app.repositories.storage_cleanup_repo import CleanupClaim, StorageCleanupJobRepository
from app.services.document_deletion_service import snapshot_storage_locator
from app.services.storage import get_storage, ObjectStorage, S3Storage, StorageSafetyError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupFailure:
    status: CleanupStatus
    code: str
    message: str


def classify_cleanup_error(exc: Exception) -> CleanupFailure:
    # Never persist str(exc): SDK URLs, SQL parameters or OS paths can contain secrets.
    if isinstance(exc, StorageSafetyError):
        return CleanupFailure(CleanupStatus.BLOCKED, exc.code, "Storage safety validation failed")
    if isinstance(exc, (TimeoutError, ConnectionError, ConnectionClosedError, ConnectTimeoutError,
                        EndpointConnectionError, ProxyConnectionError, ReadTimeoutError)):
        return CleanupFailure(CleanupStatus.RETRY, "storage_unavailable", "Storage request interrupted")
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        if status == 429 or status >= 500 or code in {
            "SlowDown", "Throttling", "ThrottlingException", "RequestLimitExceeded",
            "RequestTimeout", "RequestTimeoutException", "RequestThrottled",
        }:
            return CleanupFailure(CleanupStatus.RETRY, "storage_transient", "Temporary storage failure")
        if code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"} or status in {401, 403}:
            return CleanupFailure(CleanupStatus.BLOCKED, "access_denied", "Storage access denied")
        if code == "NoSuchBucket":
            return CleanupFailure(CleanupStatus.BLOCKED, "missing_bucket", "Storage bucket is missing")
        return CleanupFailure(CleanupStatus.BLOCKED, "storage_request_rejected", "Unrecognized storage response")
    if isinstance(exc, PermissionError):
        return CleanupFailure(CleanupStatus.BLOCKED, "permission_denied", "Filesystem access denied")
    if isinstance(exc, OSError):
        if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.EINVAL, errno.EISDIR}:
            return CleanupFailure(CleanupStatus.BLOCKED, "invalid_local_path", "Unsafe filesystem target")
        return CleanupFailure(CleanupStatus.RETRY, "filesystem_io", "Filesystem operation failed")
    return CleanupFailure(CleanupStatus.BLOCKED, "unexpected_error", "Unexpected failure requires investigation")


def cleanup_retry_delay(attempts: int, *, jitter: Callable[[float, float], float] = random.uniform) -> float:
    # Capping the exponent first bounds both CPU and integer growth for corrupt/old jobs.
    exponent = min(max(attempts - 1, 0), 17)
    base = min(settings.CLEANUP_RETRY_MAX_SECONDS, settings.CLEANUP_RETRY_BASE_SECONDS * 2**exponent)
    return base * jitter(0.8, 1.0)


def validate_claim_target(claim: CleanupClaim) -> str:
    if claim.storage_backend != settings.STORAGE_BACKEND.lower():
        raise StorageSafetyError("target_mismatch")
    key = claim.object_key_or_location
    if not key or "\x00" in key:
        raise StorageSafetyError("invalid_object_key")
    if claim.storage_backend == "local":
        relative = Path(key)
        if relative.is_absolute() or relative.drive or ".." in relative.parts or not relative.parts:
            raise StorageSafetyError("invalid_local_path")
        location = str(Path(settings.UPLOAD_DIR).resolve() / relative)
    else:
        location = key
    try:
        expected = snapshot_storage_locator(location)
    except (ValueError, RuntimeError) as exc:
        raise StorageSafetyError("invalid_storage_locator") from exc
    actual = {
        "storage_backend": claim.storage_backend,
        "storage_target_identity": claim.storage_target_identity,
        "storage_bucket_or_root": claim.storage_bucket_or_root,
        "object_key_or_location": key,
    }
    if actual != expected:
        raise StorageSafetyError("target_mismatch")
    return location


class StorageCleanupService:
    def __init__(
        self, session_factory: Callable[[], Session], *,
        storage_factory: Callable[..., ObjectStorage] = get_storage,
    ):
        self.session_factory = session_factory
        self.storage_factory = storage_factory

    def claim(self) -> CleanupClaim | None:
        with self.session_factory() as db:
            try:
                claim = StorageCleanupJobRepository(db).claim(settings.CLEANUP_LEASE_SECONDS)
                db.commit()
                return claim
            except Exception:
                db.rollback()
                raise

    def execute(self, claim: CleanupClaim) -> bool:
        try:
            location = validate_claim_target(claim)
            with self.session_factory() as db:
                repository = StorageCleanupJobRepository(db)
                if not repository.lease_is_current(claim):
                    return False
                if claim.storage_backend == "s3":
                    shared = repository.has_s3_reference(location)
                    local_locations = []
                else:
                    shared = False
                    local_locations = repository.local_locations()
                # Close the read transaction before filesystem checks and SDK calls.
            if claim.storage_backend == "local":
                shared = any(Path(other).resolve() == Path(location).resolve() for other in local_locations)
            if shared:
                raise StorageSafetyError("shared_object_reference")
            storage = self.storage_factory(cleanup=True)
            try:
                if isinstance(storage, S3Storage):
                    storage.validate_cleanup_target()
                storage.delete(location)
            finally:
                if isinstance(storage, S3Storage):
                    storage.client.close()
        except Exception as exc:
            # DB outages are not storage failures and must leave the lease recoverable.
            if isinstance(exc, SQLAlchemyError):
                raise
            failure = classify_cleanup_error(exc)
            delay = cleanup_retry_delay(claim.attempts) if failure.status == CleanupStatus.RETRY else 0
            return self.complete(claim, failure.status, delay=delay,
                                 error_code=failure.code, error_message=failure.message)
        return self.complete(claim, CleanupStatus.DONE)

    def complete(self, claim: CleanupClaim, status: CleanupStatus, **kwargs) -> bool:
        with self.session_factory() as db:
            try:
                updated = StorageCleanupJobRepository(db).finish(claim, status, **kwargs)
                db.commit()
            except Exception:
                db.rollback()
                raise
        logger.info("event=cleanup_outcome job_id=%s status=%s lease_accepted=%s",
                    claim.id, status.value, updated)
        return updated

    def run_once(self) -> bool:
        claim = self.claim()
        if claim is None:
            return False
        self.execute(claim)
        return True
