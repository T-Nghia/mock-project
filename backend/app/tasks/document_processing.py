import uuid

from app.core.database import SessionLocal
from app.core.config import settings
from app.repositories.document_repo import DocumentRepository
from app.repositories.tag_repo import TagRepository
from app.repositories.user_repo import UserRepository
from app.services.document_service import DocumentService
from app.worker import celery_app


@celery_app.task(
    name="documents.process",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=settings.DOCUMENT_TASK_MAX_RETRIES,
    soft_time_limit=settings.DOCUMENT_TASK_TIMEOUT_SECONDS,
    time_limit=settings.DOCUMENT_TASK_TIMEOUT_SECONDS + 30,
)
def process_document(self, document_id: str) -> None:
    del self
    db = SessionLocal()
    try:
        service = DocumentService(
            doc_repo=DocumentRepository(db),
            tag_repo=TagRepository(db),
            user_repo=UserRepository(db),
        )
        service.process_document_sync(uuid.UUID(document_id))
    finally:
        db.close()
