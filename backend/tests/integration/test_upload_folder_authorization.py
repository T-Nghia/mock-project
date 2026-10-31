"""Real PostgreSQL evidence; each test owns a unique, disposable schema.

Set UPLOAD_FOLDER_TEST_DATABASE_URL to a dedicated PostgreSQL/pgvector test DB.
No application tables or shared data are truncated or deleted by this suite.
"""

import io
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from psycopg2.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.document import Document, ProcessingStatus
from app.models.folder import Folder
from app.models.tag import DocumentTag, Tag
from app.models.user import User, UserRole
from app.repositories.document_repo import DocumentRepository
from app.repositories.folder_repo import FolderRepository
from app.repositories.tag_repo import TagRepository
from app.services.document_service import DocumentService
from app.services.storage import ObjectStorage


@unittest.skipUnless(
    os.getenv("UPLOAD_FOLDER_TEST_DATABASE_URL"),
    "Set UPLOAD_FOLDER_TEST_DATABASE_URL to a dedicated PostgreSQL test database",
)
class UploadFolderPostgreSQLTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ["UPLOAD_FOLDER_TEST_DATABASE_URL"]
        cls.admin_engine = create_engine(cls.database_url)
        cls.addClassCleanup(cls.admin_engine.dispose)
        if (cls.admin_engine.dialect.name, cls.admin_engine.dialect.driver) != (
            "postgresql", "psycopg2"
        ):
            raise RuntimeError("These tests require real PostgreSQL with psycopg2")

    def setUp(self):
        self.schema = f"upload_folder_test_{uuid.uuid4().hex}"
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.addCleanup(self._drop_schema)
        self.engine = create_engine(
            self.database_url,
            connect_args={"options": f"-csearch_path={self.schema},public"},
            execution_options={"schema_translate_map": {None: self.schema}},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        user = User(
            full_name="Fix01 Teacher", email=f"fix01-{uuid.uuid4()}@example.com",
            hashed_password="unused", role=UserRole.TEACHER, is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        self.owner_id = user.id
        folder = Folder(name="Owned upload folder", owner_id=self.owner_id)
        self.db.add(folder)
        self.db.flush()
        self.folder_id = folder.id
        self.db.commit()
        self.storage = Mock(spec=ObjectStorage)
        self.storage.save_stream.return_value = "fix01-object.txt"
        self.repo = DocumentRepository(self.db)
        self.service = DocumentService(
            self.repo, TagRepository(self.db), storage=self.storage,
            folder_repo=FolderRepository(self.db),
        )

    def _drop_schema(self):
        # The identifier is generated above, never supplied by a caller or environment.
        self.assertRegex(self.schema, r"^upload_folder_test_[0-9a-f]{32}$")
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))

    def upload(self):
        return self.service.save_upload(
            file=UploadFile(filename="lesson.txt", file=io.BytesIO(b"Lesson content")),
            title="Fix01 Lesson", folder_id=self.folder_id,
            uploaded_by=self.owner_id, tags=["fix01-tag"],
        )

    def assert_failed_insert_cleaned_up(self):
        self.storage.delete.assert_called_once_with("fix01-object.txt")
        # A failed PostgreSQL transaction would reject this query without rollback.
        self.assertFalse(self.db.in_transaction())
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Tag)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(DocumentTag)), 0)
        self.assertEqual(self.db.scalar(text("SELECT 1")), 1)

    def test_migrated_schema_uses_expected_folder_fk_constraint(self):
        with self.admin_engine.connect() as connection:
            row = connection.execute(text("""
                SELECT c.conname, pg_get_constraintdef(c.oid) AS definition
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public' AND t.relname = 'documents'
                  AND c.conname = 'documents_folder_id_fkey'
            """)).one()
        self.assertEqual(row.conname, "documents_folder_id_fkey")
        self.assertIn("FOREIGN KEY (folder_id)", row.definition)
        self.assertIn("ON DELETE SET NULL", row.definition)

    def test_folder_deleted_during_object_upload_returns_404_after_real_fk_failure(self):
        def save_after_concurrent_delete(*_):
            self.assertFalse(self.db.in_transaction(), "Read transaction spans object upload")
            with Session(self.engine) as other_session:
                other_session.execute(text("SET LOCAL lock_timeout = '1s'"))
                result = other_session.execute(delete(Folder).where(Folder.id == self.folder_id))
                self.assertEqual(result.rowcount, 1)
                other_session.commit()
            return "fix01-object.txt"

        self.storage.save_stream.side_effect = save_after_concurrent_delete
        with self.assertRaises(HTTPException) as raised:
            self.upload()
        self.assertEqual(raised.exception.status_code, 404)
        error = raised.exception.__cause__
        self.assertIsInstance(error, IntegrityError)
        self.assertIsInstance(error.orig, ForeignKeyViolation)
        self.assertEqual(error.orig.pgcode, "23503")
        self.assertEqual(error.orig.diag.constraint_name, "documents_folder_id_fkey")
        self.assertEqual(error.orig.diag.table_name, "documents")
        self.assertEqual(error.orig.diag.schema_name, self.schema)
        self.assert_failed_insert_cleaned_up()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Document)), 0)
        self.assertIsNone(self.db.get(Folder, self.folder_id))

    def test_upload_api_returns_404_and_never_dispatches_after_concurrent_folder_delete(self):
        def override_db():
            yield self.db

        def save_after_concurrent_delete(*_):
            self.assertFalse(self.db.in_transaction())
            with Session(self.engine) as other_session:
                other_session.execute(text("SET LOCAL lock_timeout = '1s'"))
                other_session.execute(delete(Folder).where(Folder.id == self.folder_id))
                other_session.commit()
            return "fix01-object.txt"

        previous_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = override_db
        self.storage.save_stream.side_effect = save_after_concurrent_delete
        token = create_access_token(str(self.owner_id), UserRole.TEACHER.value)
        try:
            with (
                TestClient(app) as client,
                patch("app.services.document_service.get_storage", return_value=self.storage),
                patch("app.api.routers.documents.dispatch_document_processing") as dispatch,
            ):
                response = client.post(
                    "/documents/upload", headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("lesson.txt", b"Lesson content", "text/plain")},
                    data={"folder_id": str(self.folder_id), "tags": "must-not-be-created"},
                )
                self.assertEqual(response.status_code, 404, response.text)
                dispatch.assert_not_called()
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_override
        self.assert_failed_insert_cleaned_up()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Document)), 0)

    def assert_real_insert_error_is_preserved(self, mutate, driver_type, code, constraint=None):
        def create_invalid_document(document):
            mutate(document)
            return DocumentRepository(self.db).create(document)

        with patch.object(self.repo, "create", side_effect=create_invalid_document):
            with self.assertRaises(IntegrityError) as raised:
                self.upload()
        self.assertIsInstance(raised.exception.orig, driver_type)
        self.assertEqual(raised.exception.orig.pgcode, code)
        if constraint is not None:
            self.assertEqual(raised.exception.orig.diag.constraint_name, constraint)
        self.assert_failed_insert_cleaned_up()

    def test_real_other_fk_is_preserved_instead_of_folder_404(self):
        self.assert_real_insert_error_is_preserved(
            lambda doc: setattr(doc, "uploaded_by", uuid.uuid4()),
            ForeignKeyViolation, "23503", "documents_uploaded_by_fkey",
        )

    def test_real_not_null_violation_is_preserved_instead_of_folder_404(self):
        self.assert_real_insert_error_is_preserved(
            lambda doc: setattr(doc, "title", None), NotNullViolation, "23502",
        )

    def test_real_unique_violation_is_preserved_instead_of_folder_404(self):
        existing_id = uuid.uuid4()
        self.repo.create(Document(
            id=existing_id, title="Existing", file_path="existing.txt", file_type="txt",
            uploaded_by=self.owner_id, processing_status=ProcessingStatus.PENDING,
        ))
        self.assert_real_insert_error_is_preserved(
            lambda doc: setattr(doc, "id", existing_id), UniqueViolation, "23505", "documents_pkey",
        )
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Document)), 1)

    def test_success_preserves_owned_folder_and_tags_without_transaction_during_object_io(self):
        def save_without_open_transaction(*_):
            self.assertFalse(self.db.in_transaction())
            return "fix01-object.txt"

        self.storage.save_stream.side_effect = save_without_open_transaction
        document = self.upload()
        self.assertEqual(document.folder_id, self.folder_id)
        self.assertEqual(document.uploaded_by, self.owner_id)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Document)), 1)
        self.assertEqual(self.db.scalar(select(Tag.name)), "fix01-tag")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(DocumentTag)), 1)
        self.storage.delete.assert_not_called()
