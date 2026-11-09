"""Real PostgreSQL claims, fencing, crashes and processing/delete ordering."""

import os
import threading
import unittest
import uuid
from unittest.mock import Mock, patch

from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError

from app.models.document import Document, DocumentChunk, ProcessingStatus
from app.models.storage_cleanup import CleanupStatus, StorageCleanupJob
from app.repositories.document_repo import DocumentRepository
from app.repositories.storage_cleanup_repo import StorageCleanupJobRepository
from app.services.document_deletion_service import DocumentDeletionService
from app.services.document_dispatcher import dispatch_document_processing
from app.services.document_service import DocumentService, ProcessingOutcome
from app.services.storage import ObjectStorage
from app.services.storage_cleanup_service import StorageCleanupService
from app.tasks.document_processing import handle_processing_failure
from tests.integration.reliability_support import ReliabilityDatabaseCase


@unittest.skipUnless(os.getenv("CLEANUP_TEST_DATABASE_URL"), "Set CLEANUP_TEST_DATABASE_URL to a dedicated PostgreSQL database")
class CleanupPostgreSQLTestCase(ReliabilityDatabaseCase):
    def fake_service(self, storage=None):
        storage = storage or Mock(spec=ObjectStorage)
        return StorageCleanupService(self.sessions, storage_factory=lambda **_: storage), storage

    def test_empty_queue_and_due_time_use_postgresql_clock(self):
        self.assertIsNone(self.service.claim())
        job_id = self.queue_delete()
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE storage_cleanup_jobs SET next_attempt_at=clock_timestamp()+interval '1 hour'"))
        self.assertIsNone(self.service.claim())
        self.due(job_id)
        claim = self.service.claim()
        job = self.job(job_id)
        self.assertEqual(claim.id, job_id)
        self.assertEqual(claim.attempts, 1)
        self.assertEqual(job.status, CleanupStatus.PROCESSING)
        with self.sessions() as db:
            remaining = db.scalar(select(StorageCleanupJob.lease_expires_at - func.clock_timestamp()).where(StorageCleanupJob.id == job_id))
        self.assertGreater(remaining.total_seconds(), 115)
        self.assertLessEqual(remaining.total_seconds(), 120)

    def test_initial_due_time_uses_db_clock_despite_skewed_api_clock(self):
        from datetime import datetime, timezone

        class FutureClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2099, 1, 1, tzinfo=timezone.utc)

        with patch("app.models.storage_cleanup.datetime", FutureClock):
            job_id = self.queue_delete()
        self.assertEqual(self.job(job_id).created_at.year, 2099)
        self.assertLess(self.job(job_id).next_attempt_at.year, 2099)
        self.assertEqual(self.service.claim().id, job_id)

    def test_skip_locked_does_not_wait_for_uncommitted_claim_and_rollback_recovers_it(self):
        first = self.queue_delete()
        with self.sessions() as db:
            document = Document(title="Second", file_path=uuid.uuid4().hex + ".txt", file_type="txt",
                                uploaded_by=self.actor.id, processing_status=ProcessingStatus.PENDING)
            db.add(document)
            db.flush()
            second_document = document.id
            db.commit()
        second = self.queue_delete(second_document)
        with self.sessions() as locked:
            claimed = StorageCleanupJobRepository(locked).claim(120)
            self.assertEqual(claimed.id, first)
            other = self.service.claim()
            self.assertEqual(other.id, second)
            locked.rollback()
        self.assertEqual(self.job(first).attempts, 0)
        self.assertEqual(self.service.claim().id, first)

    def test_two_workers_claim_single_job_once_with_a_real_barrier(self):
        job_id = self.queue_delete()
        barrier = threading.Barrier(3)
        results, errors = [], []

        def claim():
            try:
                barrier.wait(5)
                results.append(self.service.claim())
            except Exception as exc:
                errors.append(exc)

        workers = [threading.Thread(target=claim) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait(5)
        for worker in workers:
            worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        claims = [claim for claim in results if claim is not None]
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].id, job_id)
        self.assertEqual(self.job(job_id).attempts, 1)

    def test_I15_expired_and_wrong_tokens_cannot_complete_or_overwrite_new_worker(self):
        job_id = self.queue_delete()
        old = self.service.claim()
        with self.sessions() as db:
            from dataclasses import replace
            self.assertFalse(StorageCleanupJobRepository(db).finish(replace(old, lease_token=uuid.uuid4()), CleanupStatus.DONE))
            db.commit()
        self.expire(job_id)
        self.assertFalse(self.service.complete(old, CleanupStatus.DONE))
        fresh = self.service.claim()
        self.assertNotEqual(old.lease_token, fresh.lease_token)
        self.assertEqual(fresh.attempts, 2)
        service, storage = self.fake_service()
        self.assertFalse(service.execute(old))
        storage.delete.assert_not_called()
        self.assertTrue(service.execute(fresh))
        self.assertFalse(service.complete(old, CleanupStatus.RETRY, delay=1, error_code="stale"))
        final = self.job(job_id)
        self.assertEqual(final.status, CleanupStatus.DONE)
        self.assertIsNotNone(final.completed_at)
        self.assertIsNone(final.lease_token)
        self.assertIsNone(final.last_error_code)

    def test_retry_is_durable_and_does_not_drop_large_attempt_counts(self):
        job_id = self.queue_delete()
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE storage_cleanup_jobs SET attempts=1000000"))
        service, storage = self.fake_service()
        storage.delete.side_effect = TimeoutError("never-log-storage-secret")
        claim = service.claim()
        with self.assertLogs("app.services.storage_cleanup_service", level="INFO") as logs:
            service.execute(claim)
        job = self.job(job_id)
        self.assertEqual(job.status, CleanupStatus.RETRY)
        self.assertEqual(job.attempts, 1000001)
        self.assertNotIn("never-log", job.last_error_message)
        self.assertNotIn("never-log", " ".join(logs.output))
        with self.sessions() as db:
            remaining = db.scalar(select(StorageCleanupJob.next_attempt_at - func.clock_timestamp()).where(StorageCleanupJob.id == job_id))
        self.assertGreater(remaining.total_seconds(), 2878)
        self.assertLessEqual(remaining.total_seconds(), 3600)
        self.assertIsNone(service.claim())
        self.due(job_id)
        storage.delete.side_effect = None
        service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)

    def test_completion_does_not_wait_past_lease_behind_a_locked_job(self):
        job_id = self.queue_delete()
        claim = self.service.claim()
        with self.sessions() as locker:
            locker.scalar(select(StorageCleanupJob).where(StorageCleanupJob.id == job_id).with_for_update())
            with self.sessions() as completing:
                completing.execute(text("SET LOCAL lock_timeout = '1s'"))
                self.assertFalse(StorageCleanupJobRepository(completing).finish(claim, CleanupStatus.DONE))
                completing.commit()
            locker.rollback()
        self.assertEqual(self.job(job_id).status, CleanupStatus.PROCESSING)
        self.expire(job_id)
        self.assertFalse(self.service.complete(claim, CleanupStatus.DONE))

    def test_I24_shared_live_object_reference_is_blocked(self):
        job_id = self.queue_delete()
        with self.sessions() as db:
            db.add(Document(title="Other live reference", file_path=self.key, file_type="txt",
                            uploaded_by=self.actor.id, processing_status=ProcessingStatus.PENDING))
            db.commit()
        service, storage = self.fake_service()
        service.run_once()
        job = self.job(job_id)
        self.assertEqual(job.status, CleanupStatus.BLOCKED)
        self.assertEqual(job.last_error_code, "shared_object_reference")
        storage.delete.assert_not_called()

    def test_unknown_storage_error_is_blocked_without_exception_text(self):
        job_id = self.queue_delete()
        service, storage = self.fake_service()
        storage.delete.side_effect = RuntimeError("secret-password")
        service.run_once()
        job = self.job(job_id)
        self.assertEqual(job.status, CleanupStatus.BLOCKED)
        self.assertEqual(job.last_error_code, "unexpected_error")
        self.assertNotIn("secret-password", job.last_error_message)

    def test_storage_io_has_no_open_session_transaction(self):
        self.queue_delete()
        opened = []

        def sessions():
            db = self.sessions()
            opened.append(db)
            return db

        storage = Mock(spec=ObjectStorage)

        def delete(_):
            self.assertTrue(opened)
            self.assertTrue(all(not db.in_transaction() for db in opened))

        storage.delete.side_effect = delete
        service = StorageCleanupService(sessions, storage_factory=lambda **_: storage)
        service.run_once()
        storage.delete.assert_called_once()

    def test_I05_I06_api_process_crashes_preserve_transaction_boundary(self):
        before = self.fault_process("api_before_commit", self.document_id)
        self.assertEqual(before.returncode, 71)
        self.assertEqual(self.count(Document), 1)
        self.assertEqual(self.count(StorageCleanupJob), 0)
        after = self.fault_process("api_after_commit", self.document_id)
        self.assertEqual(after.returncode, 72)
        self.assertEqual(self.count(Document), 0)
        self.assertEqual(self.count(StorageCleanupJob), 1)

    def test_I12_crash_before_and_after_claim_commit_is_recoverable(self):
        job_id = self.queue_delete()
        before = self.fault_process("claim_before_commit", job_id)
        self.assertEqual(before.returncode, 73)
        self.assertEqual(self.job(job_id).status, CleanupStatus.PENDING)
        self.assertEqual(self.job(job_id).attempts, 0)
        after = self.fault_process("claim_after_commit", job_id)
        self.assertEqual(after.returncode, 74)
        self.assertEqual(self.job(job_id).status, CleanupStatus.PROCESSING)
        self.assertIsNone(self.service.claim())
        self.expire(job_id)
        service, storage = self.fake_service()
        service.run_once()
        storage.delete.assert_called_once_with(self.key)
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)

    def test_I18_real_connection_loss_during_completion_keeps_recoverable_lease(self):
        job_id = self.queue_delete()
        service, _ = self.fake_service()
        claim = service.claim()
        original = StorageCleanupJobRepository.finish

        def terminate_then_finish(repository, *args, **kwargs):
            pid = repository.db.scalar(text("SELECT pg_backend_pid()"))
            with self.admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as killer:
                self.assertTrue(killer.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}))
            return original(repository, *args, **kwargs)

        with patch.object(StorageCleanupJobRepository, "finish", terminate_then_finish):
            with self.assertRaises(DBAPIError):
                service.execute(claim)
        self.assertEqual(self.job(job_id).status, CleanupStatus.PROCESSING)
        self.expire(job_id)
        service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)

    def test_I10_delete_during_embedding_stops_writes_and_failure_handler_after_delete(self):
        entered, resume = threading.Event(), threading.Event()
        results, errors = [], []
        storage = Mock(spec=ObjectStorage)
        import tempfile
        from pathlib import Path
        from contextlib import contextmanager

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lesson.txt"
            path.write_text("A real PostgreSQL processing test with controlled embeddings.")

            @contextmanager
            def materialize(*_, **__):
                yield path

            storage.materialize.side_effect = materialize

            def process():
                try:
                    with self.sessions() as db:
                        provider = Mock()

                        def embed(texts, **_):
                            self.assertFalse(db.in_transaction())
                            entered.set()
                            self.assertTrue(resume.wait(10))
                            return [[0.1] * 384 for _ in texts]

                        provider.embed_batch.side_effect = embed
                        service = DocumentService(DocumentRepository(db), None, storage=storage, embedding_provider=provider)
                        results.append(service.process_document_sync(self.document_id))
                except Exception as exc:
                    errors.append(exc)

            worker = threading.Thread(target=process)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                self.queue_delete()
            finally:
                resume.set()
                worker.join(10)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results, [ProcessingOutcome.DOCUMENT_DELETED])
        self.assertEqual(self.count(DocumentChunk), 0)
        task = Mock()
        task.request.retries = 0
        task.max_retries = 5
        with self.sessions() as db:
            outcome = handle_processing_failure(task, DocumentRepository(db), self.document_id, TimeoutError("late failure"))
        self.assertEqual(outcome, ProcessingOutcome.DOCUMENT_DELETED)
        task.retry.assert_not_called()

    def test_I11_chunk_insert_holds_document_lock_and_delete_cascades_committed_chunks(self):
        inserted, release = threading.Event(), threading.Event()
        errors, results, deleting_pid = [], {}, {}

        def pause_insert(connection, _cursor, statement, *_):
            if statement.startswith("INSERT INTO") and "document_chunks" in statement:
                inserted.set()
                self.assertTrue(release.wait(10))

        event.listen(self.engine, "before_cursor_execute", pause_insert)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", pause_insert)

        def write():
            try:
                with self.sessions() as db:
                    results["write"] = DocumentRepository(db).add_chunks(self.document_id, [DocumentChunk(
                        document_id=self.document_id, chunk_index=0, content="Concurrent chunk",
                    )])
            except Exception as exc:
                errors.append(exc)

        def remove():
            try:
                with self.sessions() as db:
                    deleting_pid["pid"] = db.scalar(text("SELECT pg_backend_pid()"))
                    deleting_pid["ready"].set()
                    DocumentDeletionService(db).delete_document(self.document_id, self.actor)
                    results["delete"] = True
            except Exception as exc:
                errors.append(exc)
                deleting_pid["ready"].set()

        deleting_pid["ready"] = threading.Event()
        writer, deleter = threading.Thread(target=write), threading.Thread(target=remove)
        writer.start()
        try:
            self.assertTrue(inserted.wait(5))
            deleter.start()
            self.assertTrue(deleting_pid["ready"].wait(5))
            self.wait_for_lock(deleting_pid["pid"])
        finally:
            release.set()
            writer.join(10)
            if deleter.ident is not None:
                deleter.join(10)
        self.assertFalse(writer.is_alive() or deleter.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, {"write": True, "delete": True})
        self.assertEqual(self.count(DocumentChunk), 0)
        with self.sessions() as db:
            repository = DocumentRepository(db)
            self.assertFalse(repository.add_chunks(self.document_id, [DocumentChunk(
                document_id=self.document_id, chunk_index=1, content="Too late",
            )]))
            self.assertFalse(repository.update_status(self.document_id, ProcessingStatus.FAILED))
            self.assertFalse(repository.set_task_id(self.document_id, "late-task"))
            self.assertFalse(repository.delete_chunks(self.document_id))
        self.assertEqual(self.count(DocumentChunk), 0)

    def test_dispatcher_race_and_processing_started_after_delete_return_deleted(self):
        from fastapi import BackgroundTasks
        from app.core.config import settings
        with self.sessions() as db:
            service = DocumentService(DocumentRepository(db), None, storage=Mock(spec=ObjectStorage))

            def enqueue(_):
                self.assertFalse(db.in_transaction())
                self.queue_delete()
                return Mock(id="task-was-published")

            with patch.object(settings, "DOCUMENT_PROCESSING_MODE", "celery"), patch(
                "app.services.document_dispatcher.process_document.delay", side_effect=enqueue,
            ):
                result = dispatch_document_processing(service=service, document_id=self.document_id, background_tasks=BackgroundTasks())
            self.assertEqual(result, ProcessingOutcome.DOCUMENT_DELETED)
            self.assertEqual(service.process_document_sync(self.document_id), ProcessingOutcome.DOCUMENT_DELETED)
            service.storage.materialize.assert_not_called()

    def test_processing_database_failure_rolls_back_and_is_not_deleted_outcome(self):
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE FUNCTION reject_processing_update() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'controlled processing database failure'; END;
                $$
            """))
            connection.execute(text("""
                CREATE TRIGGER reject_processing_update BEFORE UPDATE ON documents
                FOR EACH ROW EXECUTE FUNCTION reject_processing_update()
            """))
        with self.sessions() as db:
            with self.assertRaises(DBAPIError):
                DocumentRepository(db).start_processing(self.document_id)
            self.assertFalse(db.in_transaction())
        self.assertEqual(self.count(Document), 1)
        self.assertEqual(self.count(DocumentChunk), 0)

    def test_retry_api_snapshot_contract_and_existing_permission_statuses(self):
        from fastapi.testclient import TestClient
        from app.core.database import get_db
        from app.core.security import create_access_token
        from app.main import app
        from app.models.user import User, UserRole
        previous = app.dependency_overrides.get(get_db)

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        with self.sessions() as db:
            student = User(full_name="Student", email=f"{uuid.uuid4()}@example.com", hashed_password="unused",
                           role=UserRole.STUDENT, is_active=True)
            other = User(full_name="Other Teacher", email=f"{uuid.uuid4()}@example.com", hashed_password="unused",
                         role=UserRole.TEACHER, is_active=True)
            db.add_all([student, other])
            db.flush()
            student_id, other_id = student.id, other.id
            db.commit()

        def headers(actor_id, role):
            return {"Authorization": "Bearer " + create_access_token(str(actor_id), role)}

        owner = headers(self.actor.id, "teacher")
        try:
            with TestClient(app) as client, patch(
                "app.api.routers.documents.dispatch_document_processing", return_value=ProcessingOutcome.PROCESSED,
            ) as dispatch:
                endpoint = f"/documents/{self.document_id}/retry"
                self.assertEqual(client.post(endpoint).status_code, 401)
                self.assertEqual(client.post("/documents/not-uuid/retry", headers=owner).status_code, 422)
                self.assertEqual(client.post(f"/documents/{uuid.uuid4()}/retry", headers=owner).status_code, 404)
                self.assertEqual(client.post(endpoint, headers=headers(student_id, "student")).status_code, 403)
                self.assertEqual(client.post(endpoint, headers=headers(other_id, "teacher")).status_code, 403)
                response = client.post(endpoint, headers=owner)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["id"], str(self.document_id))
                self.assertEqual(response.json()["processing_status"], "pending")
                self.assertNotIn("file_path", response.json())
                dispatch.assert_called_once()
                with self.sessions() as db:
                    db.get(Document, self.document_id).processing_status = ProcessingStatus.DONE
                    db.commit()
                self.assertEqual(client.post(endpoint, headers=owner).status_code, 409)
        finally:
            if previous is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous

    def test_retry_waits_for_delete_and_returns_404_without_dispatch(self):
        from fastapi.testclient import TestClient
        from app.core.database import get_db
        from app.core.security import create_access_token
        from app.main import app
        previous = app.dependency_overrides.get(get_db)
        entered = threading.Event()
        request_info, errors = {}, []

        def override_db():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db

        def capture_lock_pid(connection, _cursor, statement, *_):
            if "FOR UPDATE" in statement and "documents" in statement and "pid" not in request_info:
                request_info["pid"] = connection.connection.driver_connection.get_backend_pid()
                entered.set()

        try:
            with self.sessions() as locked, TestClient(app) as client, patch(
                "app.api.routers.documents.dispatch_document_processing",
            ) as dispatch:
                DocumentRepository(locked).get_for_update(self.document_id)
                event.listen(self.engine, "before_cursor_execute", capture_lock_pid)
                token = create_access_token(str(self.actor.id), "teacher")

                def retry():
                    try:
                        request_info["status"] = client.post(
                            f"/documents/{self.document_id}/retry", headers={"Authorization": "Bearer " + token},
                        ).status_code
                    except Exception as exc:
                        errors.append(exc)

                requester = threading.Thread(target=retry)
                requester.start()
                try:
                    self.assertTrue(entered.wait(5))
                    self.wait_for_lock(request_info["pid"])
                    DocumentDeletionService(locked).delete_document(self.document_id, self.actor)
                finally:
                    locked.rollback()
                    requester.join(10)
                    event.remove(self.engine, "before_cursor_execute", capture_lock_pid)
                self.assertFalse(requester.is_alive())
                self.assertEqual(errors, [])
                self.assertEqual(request_info["status"], 404)
                dispatch.assert_not_called()
        finally:
            if previous is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous
