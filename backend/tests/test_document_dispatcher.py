import unittest
import uuid
from unittest.mock import Mock, patch

from fastapi import BackgroundTasks

from app.core.config import settings
from app.services.document_dispatcher import dispatch_document_processing
from app.services.document_service import ProcessingOutcome
from app.tasks.document_processing import process_document


class DocumentDispatcherTestCase(unittest.TestCase):
    def setUp(self):
        self.original_mode = settings.DOCUMENT_PROCESSING_MODE

    def tearDown(self):
        settings.DOCUMENT_PROCESSING_MODE = self.original_mode

    def test_dispatches_to_celery_in_celery_mode(self):
        settings.DOCUMENT_PROCESSING_MODE = "celery"
        document_id = uuid.uuid4()
        service = Mock()

        with patch("app.services.document_dispatcher.process_document.delay") as delay:
            dispatch_document_processing(
                service=service,
                document_id=document_id,
                background_tasks=BackgroundTasks(),
            )

        delay.assert_called_once_with(str(document_id))
        service.process_document_sync.assert_not_called()

    def test_keeps_local_background_fallback_for_development(self):
        settings.DOCUMENT_PROCESSING_MODE = "background"
        document_id = uuid.uuid4()
        service = Mock()
        background_tasks = BackgroundTasks()

        dispatch_document_processing(
            service=service,
            document_id=document_id,
            background_tasks=background_tasks,
        )

        self.assertEqual(len(background_tasks.tasks), 1)

    def test_missing_document_is_not_enqueued_or_added_to_background_tasks(self):
        service, background = Mock(), BackgroundTasks()
        service.doc_repo.is_present.return_value = False
        with patch("app.services.document_dispatcher.process_document.delay") as delay:
            result = dispatch_document_processing(service=service, document_id=uuid.uuid4(), background_tasks=background)
        self.assertEqual(result, ProcessingOutcome.DOCUMENT_DELETED)
        self.assertEqual(background.tasks, [])
        delay.assert_not_called()

    def test_enqueue_failure_after_delete_is_deleted_outcome_without_failed_write(self):
        settings.DOCUMENT_PROCESSING_MODE = "celery"
        service = Mock()
        service.doc_repo.is_present.return_value = True
        service.doc_repo.update_status.return_value = False
        with patch("app.services.document_dispatcher.process_document.delay", side_effect=ConnectionError("broker down")):
            result = dispatch_document_processing(service=service, document_id=uuid.uuid4(), background_tasks=BackgroundTasks())
        self.assertEqual(result, ProcessingOutcome.DOCUMENT_DELETED)
        service.doc_repo.set_task_id.assert_not_called()

    @patch("app.tasks.document_processing.DocumentService")
    @patch("app.tasks.document_processing.SessionLocal")
    def test_worker_task_builds_fresh_session_and_closes_it(self, session_local, service_class):
        document_id = uuid.uuid4()
        db = session_local.return_value

        process_document.run(str(document_id))

        service_class.return_value.process_document_sync.assert_called_once_with(
            document_id,
            mark_failed_on_error=False,
        )
        db.close.assert_called_once_with()
