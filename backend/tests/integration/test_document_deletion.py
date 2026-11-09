"""Real PostgreSQL deletion/locking evidence, isolated in disposable schemas.

Set DELETE_TEST_DATABASE_URL to a dedicated, migrated PostgreSQL/pgvector test
database. Never point it at production/staging. No shared tables are truncated.
Storage/provider mocks verify absence of I/O; transactions and locks are real.
"""

import importlib.util
import os
from pathlib import Path
import threading
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.social import Bookmark, Comment, Rating
from app.models.storage_cleanup import CleanupStatus, StorageCleanupJob
from app.models.tag import DocumentTag, Tag
from app.models.user import User, UserRole
from app.schemas.retrieval import RetrievedChunk
from app.services.chat_service import ChatService
from app.services.document_deletion_service import DocumentDeletionService


@unittest.skipUnless(
    os.getenv("DELETE_TEST_DATABASE_URL"),
    "Set DELETE_TEST_DATABASE_URL to a dedicated PostgreSQL test database",
)
class DocumentDeletionPostgreSQLTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ["DELETE_TEST_DATABASE_URL"]
        cls.admin_engine = create_engine(cls.database_url)
        cls.addClassCleanup(cls.admin_engine.dispose)
        if (cls.admin_engine.dialect.name, cls.admin_engine.dialect.driver) != (
            "postgresql", "psycopg2"
        ):
            raise RuntimeError("Deletion locking evidence requires PostgreSQL/psycopg2")

    def setUp(self):
        storage_settings = patch.multiple(
            settings, STORAGE_BACKEND="s3", STORAGE_BUCKET="fix02-disposable-bucket",
            STORAGE_ENDPOINT_URL="http://127.0.0.1:19000", STORAGE_REGION="us-east-1",
        )
        storage_settings.start()
        self.addCleanup(storage_settings.stop)
        from tests.cleanup_fixture import certificate_fixture
        gate = patch.multiple(settings, DOCUMENT_DELETE_ENABLED=True,
                              CLEANUP_CERTIFICATE_FILE=certificate_fixture(self))
        gate.start()
        self.addCleanup(gate.stop)
        self.schema = f"document_deletion_test_{uuid.uuid4().hex}"
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
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.db.close)
        owner = User(
            full_name="Fix02 Owner", email=f"fix02-{uuid.uuid4()}@example.com",
            hashed_password="unused", role=UserRole.TEACHER, is_active=True,
        )
        self.db.add(owner)
        self.db.flush()
        self.actor = SimpleNamespace(id=owner.id, role=owner.role)
        document = Document(
            title="Durable delete", file_path="documents/lesson.txt", file_type="txt",
            uploaded_by=owner.id, processing_status=ProcessingStatus.DONE,
        )
        self.db.add(document)
        self.db.flush()
        self.document_id = document.id
        self.db.commit()
        self.service = DocumentDeletionService(self.db)

    def _drop_schema(self):
        self.assertRegex(self.schema, r"^document_deletion_test_[0-9a-f]{32}$")
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))

    def count(self, model):
        with Session(self.engine) as verifier:
            return verifier.scalar(select(func.count()).select_from(model))

    def assert_document_and_jobs(self, *, document_exists, jobs):
        with Session(self.engine) as verifier:
            self.assertEqual(verifier.get(Document, self.document_id) is not None,
                             document_exists)
            self.assertEqual(verifier.scalar(select(func.count()).select_from(StorageCleanupJob)),
                             jobs)

    def install_failure_trigger(self, table, *, at_commit=False):
        self.assertIn(table, {"documents", "storage_cleanup_jobs"})
        function = f'"{self.schema}".reject_deletion_test_write'
        with self.engine.begin() as connection:
            connection.execute(text(f"""
                CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Fix02 injected database failure'; END;
                $$
            """))
            if at_commit:
                ddl = f"""
                    CREATE CONSTRAINT TRIGGER reject_deletion_test_write
                    AFTER INSERT ON "{self.schema}"."{table}"
                    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
                    EXECUTE FUNCTION {function}()
                """
            else:
                operation = "DELETE" if table == "documents" else "INSERT"
                ddl = f"""
                    CREATE TRIGGER reject_deletion_test_write
                    BEFORE {operation} ON "{self.schema}"."{table}"
                    FOR EACH ROW EXECUTE FUNCTION {function}()
                """
            connection.execute(text(ddl))

    def test_migrated_queue_schema_has_snapshot_columns_constraints_and_partial_indexes(self):
        schema = inspect(self.admin_engine)
        columns = {column["name"]: column for column in schema.get_columns(
            "storage_cleanup_jobs", schema="public",
        )}
        self.assertEqual(set(columns), {
            "id", "document_id", "requested_by", "storage_backend", "storage_target_identity",
            "storage_bucket_or_root", "object_key_or_location", "status", "attempts",
            "next_attempt_at", "lease_token", "lease_expires_at", "created_at", "updated_at",
            "completed_at", "last_error_code", "last_error_message",
        })
        optional = {"lease_token", "lease_expires_at", "completed_at",
                    "last_error_code", "last_error_message"}
        for name, column in columns.items():
            self.assertEqual(column["nullable"], name in optional, name)
        self.assertEqual(schema.get_foreign_keys("storage_cleanup_jobs", schema="public"), [])
        unique = schema.get_unique_constraints("storage_cleanup_jobs", schema="public")
        self.assertIn(["document_id"], [constraint["column_names"] for constraint in unique])
        indexes = {index["name"]: index for index in schema.get_indexes(
            "storage_cleanup_jobs", schema="public",
        )}
        due = indexes["ix_storage_cleanup_due"]
        self.assertEqual(due["column_names"], ["next_attempt_at", "created_at"])
        self.assertIn("pending", str(due["dialect_options"]["postgresql_where"]))
        self.assertIn("retry", str(due["dialect_options"]["postgresql_where"]))
        expired = indexes["ix_storage_cleanup_expired_lease"]
        self.assertEqual(expired["column_names"], ["lease_expires_at"])
        self.assertIn("processing", str(expired["dialect_options"]["postgresql_where"]))
        checks = " ".join(item["sqltext"] for item in schema.get_check_constraints(
            "storage_cleanup_jobs", schema="public",
        ))
        for state in ("pending", "processing", "retry", "blocked", "done"):
            self.assertIn(state, checks)
        self.assertIn("attempts >= 0", checks)
        with self.admin_engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")),
                             "a7b8c9d0e1f2")

    def test_migration_downgrade_refuses_to_discard_unfinished_cleanup_intent(self):
        path = (Path(__file__).resolve().parents[2] / "alembic/versions"
                / "f6a7b8c9d0e1_add_storage_cleanup_jobs.py")
        spec = importlib.util.spec_from_file_location("fix02_queue_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        self.service.delete_document(self.document_id, self.actor)
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                with self.assertRaisesRegex(RuntimeError, "nonempty storage cleanup queue"):
                    migration.downgrade()
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    def test_delete_and_cleanup_intent_commit_once_without_storage_calls(self):
        statements = []

        def record_sql(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record_sql)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", record_sql)
        with (
            patch.object(self.db, "commit", wraps=self.db.commit) as commit,
            patch("app.services.storage.get_storage") as storage,
            patch("app.services.storage.S3Storage.delete") as s3_delete,
            patch("app.services.storage.LocalStorage.delete") as local_delete,
        ):
            self.service.delete_document(self.document_id, self.actor)
        commit.assert_called_once_with()
        storage.assert_not_called()
        s3_delete.assert_not_called()
        local_delete.assert_not_called()
        self.assertTrue(any("FOR UPDATE" in sql for sql in statements))
        insert_at = next(i for i, sql in enumerate(statements)
                         if sql.startswith("INSERT INTO") and "storage_cleanup_jobs" in sql)
        delete_at = next(i for i, sql in enumerate(statements)
                         if sql.startswith("DELETE FROM") and "documents" in sql)
        self.assertLess(insert_at, delete_at)
        self.assertFalse(self.db.in_transaction())
        self.assert_document_and_jobs(document_exists=False, jobs=1)
        with Session(self.engine) as verifier:
            job = verifier.scalar(select(StorageCleanupJob))
            self.assertEqual(job.document_id, self.document_id)
            self.assertEqual(job.requested_by, self.actor.id)
            self.assertEqual(job.storage_backend, "s3")
            self.assertEqual(job.storage_target_identity, "http://127.0.0.1:19000")
            self.assertEqual(job.storage_bucket_or_root, "fix02-disposable-bucket")
            self.assertEqual(job.object_key_or_location, "documents/lesson.txt")
            self.assertEqual(job.status, CleanupStatus.PENDING)
            self.assertEqual(job.attempts, 0)
            self.assertIsNone(job.lease_token)
            self.assertIsNone(job.completed_at)

    def test_job_insert_failure_rolls_back_document_deletion(self):
        self.install_failure_trigger("storage_cleanup_jobs")
        with self.assertRaises(DBAPIError):
            self.service.delete_document(self.document_id, self.actor)
        self.assertFalse(self.db.in_transaction())
        self.assert_document_and_jobs(document_exists=True, jobs=0)

    def test_document_delete_failure_rolls_back_inserted_cleanup_job(self):
        self.install_failure_trigger("documents")
        with self.assertRaises(DBAPIError):
            self.service.delete_document(self.document_id, self.actor)
        self.assertFalse(self.db.in_transaction())
        self.assert_document_and_jobs(document_exists=True, jobs=0)

    def test_deferred_database_commit_failure_is_propagated(self):
        self.install_failure_trigger("storage_cleanup_jobs", at_commit=True)
        with self.assertRaises(DBAPIError):
            self.service.delete_document(self.document_id, self.actor)
        self.assertFalse(self.db.in_transaction())
        self.assert_document_and_jobs(document_exists=True, jobs=0)

    def test_unauthorized_actor_and_repeated_delete_have_no_extra_intent(self):
        stranger = SimpleNamespace(id=uuid.uuid4(), role=UserRole.TEACHER)
        with self.assertRaises(HTTPException) as denied:
            self.service.delete_document(self.document_id, stranger)
        self.assertEqual(denied.exception.status_code, 403)
        self.assert_document_and_jobs(document_exists=True, jobs=0)
        self.service.delete_document(self.document_id, self.actor)
        with self.assertRaises(HTTPException) as repeated:
            self.service.delete_document(self.document_id, self.actor)
        self.assertEqual(repeated.exception.status_code, 404)
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    def test_authentication_autobegin_and_api_error_contract(self):
        previous = app.dependency_overrides.get(get_db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(self._restore_override, previous)
        headers = {"Authorization": "Bearer " + create_access_token(
            str(self.actor.id), self.actor.role.value,
        )}
        with TestClient(app, raise_server_exceptions=False) as client:
            self.assertEqual(client.delete(f"/documents/{self.document_id}").status_code, 401)
            self.assertEqual(client.delete("/documents/not-a-uuid", headers=headers).status_code, 422)
            self.assertEqual(client.delete(f"/documents/{uuid.uuid4()}", headers=headers).status_code,
                             404)
            with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
                response = client.delete(f"/documents/{self.document_id}", headers=headers)
            self.assertEqual(response.status_code, 204, response.text)
            self.assertEqual(response.content, b"")
            commit.assert_called_once_with()
            self.assertEqual(client.delete(f"/documents/{self.document_id}", headers=headers).status_code,
                             404)
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    @staticmethod
    def _restore_override(previous):
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous

    def test_api_database_failure_returns_500_instead_of_204_or_404(self):
        previous = app.dependency_overrides.get(get_db)

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(self._restore_override, previous)
        self.install_failure_trigger("documents")
        headers = {"Authorization": "Bearer " + create_access_token(
            str(self.actor.id), self.actor.role.value,
        )}
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.delete(f"/documents/{self.document_id}", headers=headers)
        self.assertEqual(response.status_code, 500, response.text)
        self.assert_document_and_jobs(document_exists=True, jobs=0)

    def test_postgresql_row_lock_serializes_concurrent_deletes(self):
        # First request has already locked the row before the second starts.
        self.db.scalar(select(Document).where(Document.id == self.document_id).with_for_update())
        started = threading.Event()
        result = {}

        def concurrent_delete():
            try:
                with Session(self.engine, autoflush=False) as db:
                    db.execute(text("SET LOCAL lock_timeout = '5s'"))
                    result["pid"] = db.scalar(text("SELECT pg_backend_pid()"))
                    started.set()
                    try:
                        DocumentDeletionService(db).delete_document(self.document_id, self.actor)
                        result["status"] = 204
                    except HTTPException as exc:
                        result["status"] = exc.status_code
            except Exception as exc:
                result["error"] = exc
                started.set()

        worker = threading.Thread(target=concurrent_delete, daemon=True)
        worker.start()
        try:
            self.assertTrue(started.wait(2), "Concurrent request never started")
            self.assertNotIn("error", result)
            deadline = time.monotonic() + 3
            waiting = False
            while time.monotonic() < deadline:
                with self.admin_engine.connect() as monitor:
                    waiting = monitor.scalar(text("""
                        SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid
                    """), {"pid": result["pid"]})
                if waiting:
                    break
                time.sleep(0.02)
            self.assertTrue(waiting, "PostgreSQL did not report the second DELETE waiting on a lock")
            self.service.delete_document(self.document_id, self.actor)
        finally:
            self.db.rollback()
            worker.join(6)
        self.assertFalse(worker.is_alive())
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], 404)
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    def test_hard_delete_preserves_chat_snapshots_and_cascades_document_dependents(self):
        chat = ChatSession(user_id=self.actor.id, document_id=self.document_id, title="Keep chat")
        tag = Tag(name="retained-tag")
        self.db.add_all([chat, tag])
        self.db.flush()
        chat_id = chat.id
        sources = [{"chunk_id": str(uuid.uuid4()), "chunk_index": 0,
                    "quote": "Historical citation snapshot", "score": 0.9, "heading_path": []}]
        self.db.add_all([
            DocumentChunk(document_id=self.document_id, chunk_index=0, content="Source content"),
            DocumentTag(document_id=self.document_id, tag_id=tag.id),
            Bookmark(user_id=self.actor.id, document_id=self.document_id),
            Comment(user_id=self.actor.id, document_id=self.document_id, content="Old comment"),
            Rating(user_id=self.actor.id, document_id=self.document_id, score=5),
            ChatMessage(session_id=chat_id, role="user", content="Original question"),
            ChatMessage(session_id=chat_id, role="assistant", content="Original answer",
                        source_chunks=sources),
        ])
        self.db.commit()
        self.service.delete_document(self.document_id, self.actor)
        for model in (DocumentChunk, DocumentTag, Bookmark, Comment, Rating):
            self.assertEqual(self.count(model), 0, model.__name__)
        self.assertEqual(self.count(Tag), 1)
        with Session(self.engine) as verifier:
            self.assertIsNone(verifier.get(ChatSession, chat_id).document_id)
            messages = verifier.scalars(select(ChatMessage).where(ChatMessage.session_id == chat_id)).all()
            self.assertEqual(len(messages), 2)
            assistant = next(message for message in messages if message.role == "assistant")
            self.assertEqual(assistant.source_chunks, sources)
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    def test_cleanup_intent_survives_requesting_user_hard_delete(self):
        self.service.delete_document(self.document_id, self.actor)
        with Session(self.engine) as db:
            db.execute(delete(User).where(User.id == self.actor.id))
            db.commit()
        self.assertEqual(self.count(User), 0)
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    def create_ready_chat(self):
        chunk = DocumentChunk(
            document_id=self.document_id, chunk_index=0, content="Retained source",
            embedding=[0.1] * 384,
        )
        self.db.add(chunk)
        self.db.commit()
        retriever, provider = Mock(), Mock()
        service = ChatService(self.db, retriever, provider)
        chat_id = service.create_session(document_id=self.document_id, current_user=self.actor).id
        self.db.rollback()
        retriever.retrieve.return_value = [RetrievedChunk(
            chunk_id=chunk.id, document_id=self.document_id, chunk_index=0,
            content="Retained source", score=0.9,
        )]
        self.db.rollback()
        return service, chat_id, retriever, provider

    def test_create_session_waits_for_document_delete_then_returns_404(self):
        self.db.add(DocumentChunk(
            document_id=self.document_id, chunk_index=0, content="Source",
            embedding=[0.1] * 384,
        ))
        self.db.commit()
        self.db.scalar(select(Document).where(Document.id == self.document_id).with_for_update())
        started = threading.Event()
        result = {}

        def create_session():
            try:
                with Session(self.engine, autoflush=False) as db:
                    db.execute(text("SET LOCAL lock_timeout = '5s'"))
                    result["pid"] = db.scalar(text("SELECT pg_backend_pid()"))
                    started.set()
                    try:
                        ChatService(db, Mock(), Mock()).create_session(
                            document_id=self.document_id, current_user=self.actor,
                        )
                        result["status"] = 201
                    except HTTPException as exc:
                        result["status"] = exc.status_code
            except Exception as exc:
                result["error"] = exc
                started.set()

        worker = threading.Thread(target=create_session, daemon=True)
        worker.start()
        try:
            self.assertTrue(started.wait(2))
            self.assertNotIn("error", result)
            deadline = time.monotonic() + 3
            waiting = False
            while time.monotonic() < deadline:
                with self.admin_engine.connect() as monitor:
                    waiting = monitor.scalar(text("""
                        SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid
                    """), {"pid": result["pid"]})
                if waiting:
                    break
                time.sleep(0.02)
            self.assertTrue(waiting, "Chat creation did not serialize on the real document lock")
            self.service.delete_document(self.document_id, self.actor)
        finally:
            self.db.rollback()
            worker.join(6)
        self.assertFalse(worker.is_alive())
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], 404)
        self.assertEqual(self.count(ChatSession), 0)
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    def test_document_delete_during_provider_call_succeeds_without_held_lock_and_discards_answer(self):
        service, chat_id, retriever, provider = self.create_ready_chat()

        def answer_while_document_is_deleted(**_):
            self.assertFalse(self.db.in_transaction(), "LLM call holds a database transaction")
            with Session(self.engine, autoflush=False) as deleting:
                deleting.execute(text("SET LOCAL lock_timeout = '1s'"))
                DocumentDeletionService(deleting).delete_document(self.document_id, self.actor)
            return SimpleNamespace(grounded=True, content="Late answer", source_chunk_indexes=[0])

        provider.answer.side_effect = answer_while_document_is_deleted
        with self.assertRaises(HTTPException) as raised:
            service.ask(session_id=chat_id, content="In-flight question", current_user=self.actor)
        self.assertEqual(raised.exception.status_code, 409)
        retriever.retrieve.assert_called_once()
        provider.answer.assert_called_once()
        self.assertFalse(self.db.in_transaction())
        with Session(self.engine) as verifier:
            self.assertIsNone(verifier.get(ChatSession, chat_id).document_id)
            messages = verifier.scalars(select(ChatMessage).where(ChatMessage.session_id == chat_id)).all()
            self.assertEqual([(message.role, message.content) for message in messages],
                             [("user", "In-flight question")])
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    def test_document_deleted_during_retrieval_rejects_message_before_provider(self):
        service, chat_id, retriever, provider = self.create_ready_chat()
        chunks = retriever.retrieve.return_value

        def retrieve_while_document_is_deleted(**_):
            self.assertFalse(self.db.in_transaction())
            with Session(self.engine, autoflush=False) as deleting:
                deleting.execute(text("SET LOCAL lock_timeout = '1s'"))
                DocumentDeletionService(deleting).delete_document(self.document_id, self.actor)
            return chunks

        retriever.retrieve.side_effect = retrieve_while_document_is_deleted
        with self.assertRaises(HTTPException) as raised:
            service.ask(session_id=chat_id, content="Question before delete", current_user=self.actor)
        self.assertEqual(raised.exception.status_code, 409)
        provider.answer.assert_not_called()
        self.assertEqual(self.count(ChatMessage), 1)
        self.assert_document_and_jobs(document_exists=False, jobs=1)

    def test_session_deleted_during_provider_call_does_not_recreate_messages(self):
        service, chat_id, _retriever, provider = self.create_ready_chat()

        def answer_while_session_is_deleted(**_):
            self.assertFalse(self.db.in_transaction())
            with Session(self.engine, autoflush=False) as deleting:
                deleting.execute(text("SET LOCAL lock_timeout = '1s'"))
                ChatService(deleting, Mock(), Mock()).delete_session(
                    session_id=chat_id, current_user=self.actor,
                )
            return SimpleNamespace(grounded=True, content="Late answer", source_chunk_indexes=[0])

        provider.answer.side_effect = answer_while_session_is_deleted
        with self.assertRaises(HTTPException) as raised:
            service.ask(session_id=chat_id, content="In-flight question", current_user=self.actor)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(self.count(ChatSession), 0)
        self.assertEqual(self.count(ChatMessage), 0)
        self.assert_document_and_jobs(document_exists=True, jobs=0)

    def test_preexisting_orphan_can_be_listed_read_and_deleted_only_by_owner(self):
        chat = ChatSession(user_id=self.actor.id, document_id=None, title="Legacy orphan")
        self.db.add(chat)
        self.db.flush()
        chat_id = chat.id
        citation = {"chunk_id": str(uuid.uuid4()), "chunk_index": 4,
                    "quote": "Snapshot of a removed source", "score": 0.7, "heading_path": []}
        self.db.add(ChatMessage(session_id=chat_id, role="assistant", content="Kept answer",
                                source_chunks=[citation]))
        self.db.commit()
        provider, retriever = Mock(), Mock()
        service = ChatService(self.db, retriever, provider)
        page = service.list_sessions(current_user=self.actor, limit=1, offset=0)
        self.assertEqual(page.total, 1)
        self.assertEqual([session.id for session in page.items], [chat_id])
        self.assertIsNone(page.items[0].document_id)
        transcript = service.get_session(session_id=chat_id, current_user=self.actor)
        self.assertIsNone(transcript.document_id)
        self.assertEqual(transcript.messages[0].sources[0].quote, citation["quote"])
        stranger = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN)
        self.assertEqual(service.list_sessions(current_user=stranger, limit=20, offset=0).total, 0)
        for operation in (service.get_session, service.delete_session):
            with self.assertRaises(HTTPException) as denied:
                operation(session_id=chat_id, current_user=stranger)
            self.assertEqual(denied.exception.status_code, 404)
        with self.assertRaises(HTTPException) as readonly:
            service.ask(session_id=chat_id, content="Must not send", current_user=self.actor)
        self.assertEqual(readonly.exception.status_code, 409)
        retriever.retrieve.assert_not_called()
        provider.answer.assert_not_called()
        self.assertEqual(self.count(ChatMessage), 1)
        service.delete_session(session_id=chat_id, current_user=self.actor)
        self.assertEqual(self.count(ChatSession), 0)
        self.assertEqual(self.count(ChatMessage), 0)
        with self.assertRaises(HTTPException) as repeated:
            service.delete_session(session_id=chat_id, current_user=self.actor)
        self.assertEqual(repeated.exception.status_code, 404)
