import uuid

from app.core.database import SessionLocal
from app.repositories.document_repo import DocumentRepository
from app.repositories.tag_repo import TagRepository
from app.repositories.user_repo import UserRepository
from app.services.document_service import DocumentService
from app.worker import celery_app


@celery_app.task(name="documents.process", acks_late=True)
def process_document(document_id: str) -> None:
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
