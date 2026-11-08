import random
import uuid

import httpx
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.document import ProcessingStatus
from app.repositories.document_repo import DocumentRepository
from app.repositories.tag_repo import TagRepository
from app.repositories.user_repo import UserRepository
from app.services.document_service import DocumentService, ProcessingOutcome
from app.services.gemini_embedding_provider import GeminiEmbeddingProviderError
from app.worker import celery_app


def is_retryable_processing_error(exc: Exception) -> bool:
    """Return whether rerunning the complete document job can recover."""
    if isinstance(exc, GeminiEmbeddingProviderError):
        return exc.retryable
    if isinstance(exc, DBAPIError):
        return (isinstance(exc, OperationalError) or exc.connection_invalidated
                or getattr(exc.orig, "pgcode", None) in {"40001", "40P01"})
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    if isinstance(exc, ClientError):
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        return status_code == 429 or status_code >= 500
    return isinstance(
        exc,
        (
            ConnectionClosedError,
            ConnectTimeoutError,
            EndpointConnectionError,
            ReadTimeoutError,
        ),
    )


def retry_countdown(retries: int) -> int:
    """Exponential 30-300 second delay plus up to 20 percent jitter."""
    base = min(30 * (2**min(max(retries, 0), 4)), 300)
    return base + random.randint(0, max(1, base // 5))


def handle_processing_failure(task, repository, document_id: uuid.UUID, exc: Exception):
    can_retry = is_retryable_processing_error(exc) and task.request.retries < task.max_retries
    try:
        exists = repository.update_status(
            document_id,
            ProcessingStatus.RETRYING if can_retry else ProcessingStatus.FAILED,
            last_error=str(exc),
        )
    except DBAPIError as state_error:
        # A DB outage is not proof that DELETE committed. Retry under the
        # existing policy even when recording RETRYING is temporarily impossible.
        if is_retryable_processing_error(state_error) and task.request.retries < task.max_retries:
            raise task.retry(exc=state_error, countdown=retry_countdown(task.request.retries))
        raise
    if not exists:
        return ProcessingOutcome.DOCUMENT_DELETED
    if not can_retry:
        raise exc
    try:
        raise task.retry(
            exc=exc,
            countdown=retry_countdown(task.request.retries),
        )
    except MaxRetriesExceededError:
        if not repository.update_status(document_id, ProcessingStatus.FAILED, last_error=str(exc)):
            return ProcessingOutcome.DOCUMENT_DELETED
        raise


@celery_app.task(
    name="documents.process",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=settings.DOCUMENT_TASK_MAX_RETRIES,
    soft_time_limit=settings.DOCUMENT_TASK_TIMEOUT_SECONDS,
    time_limit=settings.DOCUMENT_TASK_TIMEOUT_SECONDS + 30,
)
def process_document(self, document_id: str) -> str:
    db = SessionLocal()
    try:
        repository = DocumentRepository(db)
        service = DocumentService(
            doc_repo=repository,
            tag_repo=TagRepository(db),
            user_repo=UserRepository(db),
        )
        parsed_document_id = uuid.UUID(document_id)
        try:
            outcome = service.process_document_sync(
                parsed_document_id,
                mark_failed_on_error=False,
            )
            return outcome.value
        except Exception as exc:
            db.rollback()
            outcome = handle_processing_failure(self, repository, parsed_document_id, exc)
            return outcome.value
    finally:
        db.close()
