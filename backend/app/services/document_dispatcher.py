import uuid

from fastapi import BackgroundTasks

from app.core.config import settings
from app.models.document import ProcessingStatus
from app.services.document_service import DocumentService, ProcessingOutcome
from app.tasks.document_processing import process_document


def dispatch_document_processing(
    *,
    service: DocumentService,
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
) -> ProcessingOutcome:
    if not service.doc_repo.is_present(document_id):
        return ProcessingOutcome.DOCUMENT_DELETED
    if settings.DOCUMENT_PROCESSING_MODE.lower() == "celery":
        try:
            result = process_document.delay(str(document_id))
        except Exception as exc:
            if not service.doc_repo.update_status(
                document_id, ProcessingStatus.FAILED, last_error=f"enqueue failed: {exc}"
            ):
                return ProcessingOutcome.DOCUMENT_DELETED
            raise
        if not service.doc_repo.set_task_id(document_id, result.id):
            return ProcessingOutcome.DOCUMENT_DELETED
        return ProcessingOutcome.PROCESSED
    background_tasks.add_task(service.process_document_sync, document_id)
    return ProcessingOutcome.PROCESSED
