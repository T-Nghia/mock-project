import uuid

from fastapi import BackgroundTasks

from app.core.config import settings
from app.services.document_service import DocumentService
from app.tasks.document_processing import process_document


def dispatch_document_processing(
    *,
    service: DocumentService,
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
) -> None:
    if settings.DOCUMENT_PROCESSING_MODE.lower() == "celery":
        process_document.delay(str(document_id))
        return
    background_tasks.add_task(service.process_document_sync, document_id)
