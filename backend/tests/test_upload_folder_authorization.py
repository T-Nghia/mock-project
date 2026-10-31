import io
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException, UploadFile
from psycopg2.errors import ForeignKeyViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.repositories.document_repo import DocumentRepository
from app.repositories.folder_repo import FolderRepository
from app.repositories.tag_repo import TagRepository
from app.services.document_service import DocumentService
from app.services.storage import ObjectStorage


class UploadFolderAuthorizationTestCase(unittest.TestCase):
    def setUp(self):
        self.owner_id = uuid.uuid4()
        self.folder_id = uuid.uuid4()
        self.db = Mock(spec=Session)
        self.doc_repo = Mock(spec=DocumentRepository, db=self.db)
        self.doc_repo.create.side_effect = lambda document: document
        self.folder_repo = Mock(spec=FolderRepository)
        self.tag_repo = Mock(spec=TagRepository)
        self.storage = Mock(spec=ObjectStorage)
        self.storage.save_stream.return_value = "stored.txt"
        self.service = DocumentService(
            self.doc_repo, self.tag_repo, storage=self.storage, folder_repo=self.folder_repo
        )

    def upload(self, folder_id):
        return self.service.save_upload(
            file=UploadFile(filename="lesson.txt", file=io.BytesIO(b"Lesson content")),
            title="Lesson", folder_id=folder_id, uploaded_by=self.owner_id, tags=["lesson"],
        )

    def assert_no_writes(self):
        self.storage.save_stream.assert_not_called()
        self.storage.delete.assert_not_called()
        self.doc_repo.create.assert_not_called()
        self.tag_repo.get_or_create.assert_not_called()
        self.tag_repo.attach_to_document.assert_not_called()

    def test_missing_authorization_dependency_fails_closed(self):
        self.service.folder_repo = None
        with self.assertRaisesRegex(RuntimeError, "Folder authorization repository is required"):
            self.upload(self.folder_id)
        self.assert_no_writes()

    def test_unknown_or_unowned_folder_is_rejected_before_writes(self):
        self.folder_repo.get_owned.return_value = None
        with self.assertRaises(HTTPException) as raised:
            self.upload(self.folder_id)
        self.assertEqual(raised.exception.status_code, 404)
        self.folder_repo.get_owned.assert_called_once_with(self.folder_id, self.owner_id)
        self.assert_no_writes()

    def test_ownership_precedes_storage_and_read_transaction_ends_before_object_io(self):
        events = []
        self.folder_repo.get_owned.side_effect = lambda *_: events.append("authorize") or object()
        self.db.rollback.side_effect = lambda: events.append("rollback")
        self.storage.save_stream.side_effect = lambda *_: events.append("storage") or "stored.txt"
        self.doc_repo.create.side_effect = lambda doc: events.append("insert") or doc
        document = self.upload(self.folder_id)
        self.assertEqual(events, ["authorize", "rollback", "storage", "insert"])
        self.assertEqual(document.folder_id, self.folder_id)
        self.assertEqual(document.uploaded_by, self.owner_id)

    def test_unfiled_upload_does_not_require_authorization_dependency(self):
        self.service.folder_repo = None
        document = self.upload(None)
        self.assertIsNone(document.folder_id)
        self.folder_repo.get_owned.assert_not_called()

    @staticmethod
    def integrity_error(driver_type, constraint, table="documents"):
        # Control-flow tests only; integration tests assert real PostgreSQL diagnostics.
        original = Mock(spec=driver_type)
        original.diag = SimpleNamespace(constraint_name=constraint, table_name=table)
        return IntegrityError("INSERT", {}, original)

    def test_only_document_folder_fk_is_translated_and_object_is_cleaned_once(self):
        error = self.integrity_error(ForeignKeyViolation, "documents_folder_id_fkey")
        self.doc_repo.create.side_effect = error
        with self.assertRaises(HTTPException) as raised:
            self.upload(self.folder_id)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertIs(raised.exception.__cause__, error)
        self.storage.delete.assert_called_once_with("stored.txt")
        self.tag_repo.get_or_create.assert_not_called()

    def test_other_database_errors_are_preserved_after_cleanup(self):
        errors = [
            self.integrity_error(ForeignKeyViolation, "documents_uploaded_by_fkey"),
            self.integrity_error(ForeignKeyViolation, "documents_folder_id_fkey", "other_table"),
            self.integrity_error(UniqueViolation, "documents_folder_id_fkey"),
            IntegrityError("INSERT", {}, ValueError("not a PostgreSQL FK violation")),
            OperationalError("INSERT", {}, RuntimeError("connection lost")),
            RuntimeError("unexpected persistence failure"),
        ]
        for error in errors:
            with self.subTest(error=error):
                self.storage.reset_mock()
                self.doc_repo.create.side_effect = error
                with self.assertRaises(type(error)) as raised:
                    self.upload(self.folder_id)
                self.assertIs(raised.exception, error)
                self.storage.delete.assert_called_once_with("stored.txt")
                self.tag_repo.get_or_create.assert_not_called()


class DocumentCreateRollbackTestCase(unittest.TestCase):
    def test_insert_or_commit_failure_rolls_back_and_preserves_error(self):
        for operation in ("add", "commit"):
            for error in (IntegrityError("INSERT", {}, Exception("constraint")), RuntimeError("db")):
                with self.subTest(operation=operation, error=error):
                    db = Mock(spec=Session)
                    getattr(db, operation).side_effect = error
                    with self.assertRaises(type(error)) as raised:
                        DocumentRepository(db).create(Mock())
                    self.assertIs(raised.exception, error)
                    db.rollback.assert_called_once_with()
                    db.refresh.assert_not_called()
