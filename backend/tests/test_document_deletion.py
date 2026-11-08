"""Transaction orchestration tests; real PostgreSQL locking is covered separately."""

from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base
from app.models.document import Document
from app.models.storage_cleanup import StorageCleanupJob
from app.models.user import User, UserRole
from app.services.document_deletion_service import DocumentDeletionService, snapshot_storage_locator


class DocumentDeletionTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.db.close)
        self.user = User(
            id=uuid.uuid4(), full_name="Owner", email="owner@example.com",
            hashed_password="unused", role=UserRole.TEACHER, is_active=True,
        )
        self.db.add(self.user)
        self.db.flush()
        self.document = Document(
            id=uuid.uuid4(), title="Lesson", uploaded_by=self.user.id,
            file_type="txt", file_path=str(Path(settings.UPLOAD_DIR).resolve() / "lesson.txt"),
        )
        self.db.add(self.document)
        self.db.commit()
        self.document_id = self.document.id
        self.db.rollback()
        self.actor = SimpleNamespace(id=self.user.id, role=UserRole.TEACHER)
        self.service = DocumentDeletionService(self.db)
        self.storage_patch = patch.object(settings, "STORAGE_BACKEND", "local")
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)

    def test_authentication_autobegin_commits_once_with_both_changes_staged(self):
        self.assertIsNotNone(self.db.get(User, self.actor.id))
        self.assertTrue(self.db.in_transaction())
        commit = self.db.commit
        with patch.object(self.db, "commit", wraps=commit) as commits:
            self.service.delete_document(self.document_id, self.actor)
        commits.assert_called_once_with()
        self.assertIsNone(self.db.get(Document, self.document_id))
        job = self.db.scalar(select(StorageCleanupJob))
        self.assertEqual(job.document_id, self.document_id)
        self.assertEqual(job.requested_by, self.actor.id)

    def test_job_stage_failure_rolls_back_without_delete(self):
        with patch.object(self.service.jobs, "stage", side_effect=RuntimeError("insert failed")):
            with self.assertRaisesRegex(RuntimeError, "insert failed"):
                self.service.delete_document(self.document_id, self.actor)
        self.assertFalse(self.db.in_transaction())
        self.assertIsNotNone(self.db.get(Document, self.document_id))
        self.assertIsNone(self.db.scalar(select(StorageCleanupJob)))

    def test_delete_stage_failure_rolls_back_job(self):
        with patch.object(self.service.documents, "stage_delete", side_effect=RuntimeError("delete failed")):
            with self.assertRaisesRegex(RuntimeError, "delete failed"):
                self.service.delete_document(self.document_id, self.actor)
        self.assertFalse(self.db.in_transaction())
        self.assertIsNotNone(self.db.get(Document, self.document_id))
        self.assertIsNone(self.db.scalar(select(StorageCleanupJob)))

    def test_flush_failure_rolls_back_both_and_never_commits(self):
        with (
            patch.object(self.db, "flush", side_effect=RuntimeError("flush failed")),
            patch.object(self.db, "commit") as commits,
        ):
            with self.assertRaisesRegex(RuntimeError, "flush failed"):
                self.service.delete_document(self.document_id, self.actor)
        commits.assert_not_called()
        self.assertIsNotNone(self.db.get(Document, self.document_id))
        self.assertIsNone(self.db.scalar(select(StorageCleanupJob)))

    def test_unknown_commit_acknowledgement_never_returns_success(self):
        commit = self.db.commit

        def commit_then_disconnect():
            commit()
            raise OperationalError("COMMIT", {}, RuntimeError("connection lost"))

        with (
            patch.object(self.db, "commit", side_effect=commit_then_disconnect) as commits,
            self.assertLogs("app.services.document_deletion_service", level="ERROR") as logs,
        ):
            with self.assertRaises(OperationalError):
                self.service.delete_document(self.document_id, self.actor)
        commits.assert_called_once_with()
        self.assertIn("outcome may be unknown", logs.output[0])
        self.assertIsNone(self.db.get(Document, self.document_id))
        self.assertIsNotNone(self.db.scalar(select(StorageCleanupJob)))

    def test_other_user_is_forbidden_without_creating_intent(self):
        other = SimpleNamespace(id=uuid.uuid4(), role=UserRole.TEACHER)
        with self.assertRaises(HTTPException) as error:
            self.service.delete_document(self.document_id, other)
        self.assertEqual(error.exception.status_code, 403)
        self.assertFalse(self.db.in_transaction())
        self.assertIsNotNone(self.db.get(Document, self.document_id))
        self.assertIsNone(self.db.scalar(select(StorageCleanupJob)))

    def test_repeated_delete_is_404_with_one_intent(self):
        self.service.delete_document(self.document_id, self.actor)
        with self.assertRaises(HTTPException) as error:
            self.service.delete_document(self.document_id, self.actor)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(len(self.db.scalars(select(StorageCleanupJob)).all()), 1)

    def test_pending_unrelated_write_is_rejected_without_discarding_it(self):
        pending = User(full_name="Pending", email="pending@example.com", hashed_password="unused")
        self.db.add(pending)
        with self.assertRaisesRegex(RuntimeError, "clean request session"):
            self.service.delete_document(self.document_id, self.actor)
        self.assertIn(pending, self.db.new)

    def test_explicit_and_nested_transactions_are_rejected(self):
        self.db.rollback()
        with self.db.begin():
            with self.assertRaisesRegex(RuntimeError, "clean request session"):
                self.service.delete_document(self.document_id, self.actor)
        with self.db.begin_nested():
            with self.assertRaisesRegex(RuntimeError, "clean request session"):
                self.service.delete_document(self.document_id, self.actor)

    def test_autoflush_and_external_transaction_are_rejected(self):
        with Session(self.engine) as autoflush_db:
            with self.assertRaisesRegex(RuntimeError, "clean request session"):
                DocumentDeletionService(autoflush_db).delete_document(self.document_id, self.actor)
        with self.engine.connect() as connection, connection.begin():
            with Session(connection, autoflush=False) as external_db:
                with self.assertRaisesRegex(RuntimeError, "external transaction"):
                    DocumentDeletionService(external_db).delete_document(self.document_id, self.actor)

    def test_unsupported_locator_failure_keeps_metadata(self):
        with patch.object(settings, "STORAGE_BACKEND", "unknown"):
            with self.assertRaisesRegex(RuntimeError, "Unsupported storage"):
                self.service.delete_document(self.document_id, self.actor)
        self.assertIsNotNone(self.db.get(Document, self.document_id))
        self.assertIsNone(self.db.scalar(select(StorageCleanupJob)))

    def test_cleanup_repository_only_stages(self):
        self.service.jobs.db = Mock()
        job = StorageCleanupJob(document_id=self.document_id, requested_by=self.actor.id)
        self.service.jobs.stage(job)
        self.service.jobs.db.add.assert_called_once_with(job)
        self.service.jobs.db.commit.assert_not_called()
        self.service.jobs.db.flush.assert_not_called()


class StorageLocatorTestCase(unittest.TestCase):
    def test_local_snapshot_is_anchored_to_root(self):
        root = Path("test-uploads").resolve()
        with patch.multiple(settings, STORAGE_BACKEND="local", UPLOAD_DIR=str(root)):
            locator = snapshot_storage_locator(str(root / "nested" / "lesson.txt"))
            self.assertEqual(locator["storage_bucket_or_root"], str(root))
            self.assertEqual(locator["object_key_or_location"], "nested/lesson.txt")
            with self.assertRaises(RuntimeError):
                snapshot_storage_locator(str(root.parent / "outside.txt"))
            with self.assertRaises(RuntimeError):
                snapshot_storage_locator(str(root))

    def test_s3_snapshot_excludes_credentials_and_has_endpoint_bucket_key(self):
        with patch.multiple(
            settings, STORAGE_BACKEND="s3", STORAGE_BUCKET="test-bucket",
            STORAGE_ENDPOINT_URL="https://storage.example.com:9443/s3",
            STORAGE_ACCESS_KEY_ID="never-copy-access", STORAGE_SECRET_ACCESS_KEY="never-copy-secret",
        ):
            locator = snapshot_storage_locator("prefix/lesson.txt")
        self.assertEqual(locator, {
            "storage_backend": "s3", "storage_target_identity": "https://storage.example.com:9443/s3",
            "storage_bucket_or_root": "test-bucket", "object_key_or_location": "prefix/lesson.txt",
        })
        self.assertNotIn("never-copy", str(locator))

    def test_s3_aws_target_without_custom_endpoint(self):
        with patch.multiple(settings, STORAGE_BACKEND="s3", STORAGE_BUCKET="test",
                            STORAGE_ENDPOINT_URL="", STORAGE_REGION="us-east-1"):
            self.assertEqual(snapshot_storage_locator("key")["storage_target_identity"], "aws:s3:us-east-1")

    def test_s3_rejects_signed_urls_and_credentials(self):
        with patch.multiple(settings, STORAGE_BACKEND="s3", STORAGE_BUCKET="test"):
            for endpoint in (
                "https://user:secret@example.com", "https://example.com?signature=secret",
                "file:///tmp/storage", "https://example.com#secret",
            ):
                with self.subTest(endpoint=endpoint), patch.object(settings, "STORAGE_ENDPOINT_URL", endpoint):
                    with self.assertRaises(RuntimeError):
                        snapshot_storage_locator("key")
            with patch.object(settings, "STORAGE_ENDPOINT_URL", "https://example.com"):
                with self.assertRaises(RuntimeError):
                    snapshot_storage_locator("https://example.com/key?signature=secret")
