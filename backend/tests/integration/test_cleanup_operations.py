"""Real PostgreSQL operator transactions and bounded queue observations."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
import io
import json
import os
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import func, inspect, select

from app.cleanup_operator import main
from app.core.config import settings
from app.models.storage_cleanup import CleanupStatus, StorageCleanupJob as Job, StorageCleanupRequeue as Audit
from app.services.cleanup_operations import inspect_job, queue_metrics, requeue_job
from tests.integration.reliability_support import ReliabilityDatabaseCase


@unittest.skipUnless(os.getenv("CLEANUP_TEST_DATABASE_URL"), "Requires dedicated PostgreSQL")
class CleanupOperationsTestCase(ReliabilityDatabaseCase):
    def job_with_status(self, state):
        job_id = self.queue_delete()
        with self.sessions() as db:
            job = db.get(Job, job_id)
            job.status = state
            job.attempts = 7
            job.last_error_code = "access_denied"
            job.last_error_message = "https://user:never-print-secret@storage.invalid/private-key"
            db.commit()
        return job_id

    def test_inspect_redacts_target_object_credentials_and_raw_error(self):
        job_id = self.job_with_status(CleanupStatus.BLOCKED)
        with self.sessions() as db:
            output = json.dumps(inspect_job(db, job_id))
        self.assertIn("access_denied", output)
        for forbidden in ("never-print-secret", self.key, "storage_target", "lease_token", "requested_by"):
            self.assertNotIn(forbidden, output)

    def test_dry_run_and_apply_preserve_locator_attempts_and_write_atomic_audit(self):
        job_id = self.job_with_status(CleanupStatus.BLOCKED)
        before = self.job(job_id)
        with self.sessions() as db:
            self.assertTrue(requeue_job(db, job_id, operator="ops", ticket="INC-42")["dry_run"])
        self.assertEqual(self.job(job_id).status, CleanupStatus.BLOCKED)
        self.assertEqual(self.count(Audit), 0)
        with self.sessions() as db:
            requeue_job(db, job_id, operator="ops", ticket="INC-42", apply=True)
        after = self.job(job_id)
        self.assertEqual(after.status, CleanupStatus.PENDING)
        self.assertEqual(after.attempts, 7)
        for name in ("storage_backend", "storage_target_identity", "storage_bucket_or_root", "object_key_or_location"):
            self.assertEqual(getattr(after, name), getattr(before, name))
        with self.sessions() as db:
            audit = db.scalar(select(Audit))
            self.assertEqual((audit.job_id, audit.previous_status, audit.operator, audit.ticket),
                             (job_id, "blocked", "ops", "INC-42"))

    def test_requeue_rejects_pending_processing_and_done_without_audit(self):
        job_id = self.job_with_status(CleanupStatus.BLOCKED)
        for state in (CleanupStatus.PENDING, CleanupStatus.PROCESSING, CleanupStatus.DONE):
            with self.sessions() as db:
                row = db.get(Job, job_id)
                row.status = state
                row.lease_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                db.commit()
            with self.sessions() as db, self.assertRaisesRegex(ValueError, "only_blocked_or_retry"):
                requeue_job(db, job_id, operator="ops", ticket="INC-42", apply=True)
            self.assertEqual(self.job(job_id).status, state)
        self.assertEqual(self.count(Audit), 0)

    def test_commit_failure_rolls_back_requeue_and_audit(self):
        job_id = self.job_with_status(CleanupStatus.RETRY)
        with self.sessions() as db:
            def fail_after_real_writes():
                db.flush()
                self.assertEqual(db.get(Job, job_id).status, CleanupStatus.PENDING)
                self.assertEqual(db.scalar(select(func.count()).select_from(Audit)), 1)
                raise RuntimeError("controlled failure after real writes before commit")

            with patch.object(db, "commit", side_effect=fail_after_real_writes), self.assertRaises(RuntimeError):
                requeue_job(db, job_id, operator="ops", ticket="INC-42", apply=True)
        self.assertEqual(self.job(job_id).status, CleanupStatus.RETRY)
        self.assertEqual(self.count(Audit), 0)

    def test_requeue_does_not_wait_behind_locked_job(self):
        job_id = self.job_with_status(CleanupStatus.RETRY)
        with self.sessions() as owner:
            owner.scalar(select(Job).where(Job.id == job_id).with_for_update())
            with self.sessions() as operator, self.assertRaises(Exception):
                requeue_job(operator, job_id, operator="ops", ticket="INC-42", apply=True)
        self.assertEqual(self.count(Audit), 0)

    def test_requeue_rechecks_locked_state_even_if_session_cached_retry(self):
        job_id = self.job_with_status(CleanupStatus.RETRY)
        token = uuid.uuid4()
        with self.sessions() as operator:
            cached = operator.get(Job, job_id)
            self.assertEqual(cached.status, CleanupStatus.RETRY)
            with self.sessions() as worker:
                active = worker.get(Job, job_id)
                active.status = CleanupStatus.PROCESSING
                active.lease_token = token
                active.lease_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                worker.commit()
            with self.assertRaisesRegex(ValueError, "only_blocked_or_retry"):
                requeue_job(operator, job_id, operator="ops", ticket="INC-42", apply=True)
        self.assertEqual(self.job(job_id).status, CleanupStatus.PROCESSING)
        self.assertEqual(self.job(job_id).lease_token, token)
        self.assertEqual(self.count(Audit), 0)

    def test_metrics_are_capped_sanitized_and_report_backlog_thresholds(self):
        job_id = self.job_with_status(CleanupStatus.RETRY)
        with self.sessions() as db:
            job = db.get(Job, job_id)
            job.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
            job.next_attempt_at = datetime.now(timezone.utc) - timedelta(minutes=16)
            for _ in range(3):
                db.add(Job(document_id=uuid.uuid4(), requested_by=self.actor.id, storage_backend="s3",
                           storage_target_identity="secret-target", storage_bucket_or_root="secret-bucket",
                           object_key_or_location="secret-key", status=CleanupStatus.BLOCKED))
            db.commit()
        with patch.object(settings, "CLEANUP_METRICS_LIMIT", 2), self.sessions() as db:
            result = queue_metrics(db)
        self.assertIn('slrms_cleanup_jobs{status="blocked"} 2', result)
        self.assertIn('slrms_cleanup_jobs_capped{status="blocked"} 1', result)
        self.assertIn("slrms_cleanup_warning 1", result)
        self.assertIn("slrms_cleanup_critical 1", result)
        self.assertIn("slrms_cleanup_overdue 1", result)
        self.assertIn("slrms_cleanup_retry_overdue 1", result)
        self.assertIn("slrms_cleanup_retry_overdue_capped 0", result)
        self.assertNotIn("secret", result)
        self.assertIn("ix_storage_cleanup_status_created", {index["name"] for index in inspect(self.engine).get_indexes("storage_cleanup_jobs")})

    def test_cli_default_dry_run_and_sanitized_failure(self):
        job_id = self.job_with_status(CleanupStatus.BLOCKED)
        output, error = io.StringIO(), io.StringIO()
        with patch("app.cleanup_operator.SessionLocal", self.sessions), redirect_stdout(output):
            self.assertEqual(main(["requeue", str(job_id), "--ticket", "INC-42"]), 0)
        self.assertTrue(json.loads(output.getvalue())["dry_run"])
        self.assertEqual(self.count(Audit), 0)
        with patch("app.cleanup_operator.SessionLocal", side_effect=RuntimeError("never-print-secret")), redirect_stderr(error):
            self.assertEqual(main(["inspect", str(job_id)]), 1)
        self.assertNotIn("never-print-secret", error.getvalue())
        self.assertEqual(self.job(job_id).status, CleanupStatus.BLOCKED)

    def test_metrics_expired_lease_count_and_oldest_age(self):
        job_id = self.job_with_status(CleanupStatus.PROCESSING)
        with self.sessions() as db:
            db.get(Job, job_id).status = CleanupStatus.PENDING
            db.commit()
        with self.sessions() as db:
            pending = queue_metrics(db)
        self.assertIn("slrms_cleanup_overdue 1", pending)
        self.assertIn("slrms_cleanup_retry_overdue 0", pending)
        with self.sessions() as db:
            db.get(Job, job_id).status = CleanupStatus.PROCESSING
            db.get(Job, job_id).lease_expires_at = func.clock_timestamp() - timedelta(seconds=5)
            db.commit()
        with self.sessions() as db:
            result = queue_metrics(db)
        self.assertIn("slrms_cleanup_expired_leases 1", result)
        self.assertIn("slrms_cleanup_oldest_unfinished_age_seconds", result)
