import unittest
import uuid
from unittest.mock import Mock, patch

from fastapi import BackgroundTasks

from app.core.config import settings
from app.services.document_dispatcher import dispatch_document_processing
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

    @patch("app.tasks.document_processing.DocumentService")
    @patch("app.tasks.document_processing.SessionLocal")
    def test_worker_task_builds_fresh_session_and_closes_it(self, session_local, service_class):
        document_id = uuid.uuid4()
        db = session_local.return_value

        process_document.run(str(document_id))

        service_class.return_value.process_document_sync.assert_called_once_with(document_id)
        db.close.assert_called_once_with()
