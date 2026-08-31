import uuid

from fastapi import BackgroundTasks

from app.core.config import settings
from app.models.document import ProcessingStatus
from app.services.document_service import DocumentService
from app.tasks.document_processing import process_document


def dispatch_document_processing(
    *,
    service: DocumentService,
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
) -> None:
    if settings.DOCUMENT_PROCESSING_MODE.lower() == "celery":
        document = service.doc_repo.get_by_id(document_id)
        try:
            result = process_document.delay(str(document_id))
        except Exception as exc:
            if document:
                service.doc_repo.update_status(
                    document, ProcessingStatus.FAILED, last_error=f"enqueue failed: {exc}"
                )
            raise
        if document and hasattr(service.doc_repo, "set_task_id"):
            service.doc_repo.set_task_id(document, result.id)
        return
    background_tasks.add_task(service.process_document_sync, document_id)
