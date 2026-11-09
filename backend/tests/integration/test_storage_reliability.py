"""Actual MinIO + PostgreSQL storage failures and crash recovery (no S3 mocks)."""

import os
import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError
from sqlalchemy import text

from app.core.config import settings
from app.models.storage_cleanup import CleanupStatus
from app.services.storage import S3Storage
from tests.integration.reliability_support import ReliabilityDatabaseCase
from tests.integration.s3_fault_proxy import S3FaultProxy


class S3ReliabilityDatabaseCase(ReliabilityDatabaseCase):
    def setUp(self):
        super().setUp()
        self.storage = S3Storage()
        self.addCleanup(self.storage.client.close)
        self.storage.client.create_bucket(Bucket=self.storage.bucket)
        self.addCleanup(self.remove_bucket)
        self.storage.save(self.key, b"M2 real S3 payload", "text/plain")

    def remove_bucket(self):
        # Only the uniquely created test bucket. Explicit version inventory is
        # test teardown, never part of production cleanup or object discovery.
        self.assertRegex(self.storage.bucket, r"^fix02-m2-[0-9a-f]{32}$")
        client = self.storage.client
        versions = client.list_object_versions(Bucket=self.storage.bucket)
        objects = [{"Key": row["Key"], "VersionId": row["VersionId"]}
                   for row in versions.get("Versions", []) + versions.get("DeleteMarkers", [])]
        if objects:
            client.delete_objects(Bucket=self.storage.bucket, Delete={"Objects": objects})
        current = client.list_objects_v2(Bucket=self.storage.bucket)
        for row in current.get("Contents", []):
            client.delete_object(Bucket=self.storage.bucket, Key=row["Key"])
        client.delete_bucket(Bucket=self.storage.bucket)

    def assert_object_present(self):
        self.assertEqual(self.storage.read(self.key), b"M2 real S3 payload")

    def assert_object_missing(self):
        with self.assertRaises(ClientError) as missing:
            self.storage.client.head_object(Bucket=self.storage.bucket, Key=self.key)
        self.assertEqual(missing.exception.response["ResponseMetadata"]["HTTPStatusCode"], 404)


@unittest.skipUnless(os.getenv("RUN_RELIABILITY_INTEGRATION") == "1", "Real MinIO/PostgreSQL M2 integration is opt-in")
class StorageReliabilityTestCase(S3ReliabilityDatabaseCase):
    def test_real_delete_and_already_missing_object_are_done(self):
        job_id = self.queue_delete()
        self.assertTrue(self.service.run_once())
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)
        self.assert_object_missing()
        self.storage.delete(self.key)
        self.storage.delete(self.key)

    def test_I04_http_503_is_retry_then_actual_minio_recovery(self):
        with S3FaultProxy(settings.STORAGE_ENDPOINT_URL) as proxy, patch.object(settings, "STORAGE_ENDPOINT_URL", proxy.endpoint):
            job_id = self.queue_delete()
            proxy.faults.append("503")
            self.service.run_once()
            self.assertTrue(proxy.request_seen.is_set())
            self.assertEqual(self.job(job_id).status, CleanupStatus.RETRY)
            self.assert_object_present()
            self.due(job_id)
            self.service.run_once()
            self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)
            self.assert_object_missing()

    def test_I04_real_read_timeout_is_retry_then_recovery(self):
        with S3FaultProxy(settings.STORAGE_ENDPOINT_URL) as proxy, patch.multiple(
            settings, STORAGE_ENDPOINT_URL=proxy.endpoint,
            CLEANUP_CONNECT_TIMEOUT_SECONDS=0.2, CLEANUP_READ_TIMEOUT_SECONDS=0.2,
        ):
            job_id = self.queue_delete()
            proxy.faults.append("timeout")
            self.service.run_once()
            self.assertTrue(proxy.request_seen.is_set())
            self.assertEqual(self.job(job_id).status, CleanupStatus.RETRY)
            self.assert_object_present()
            proxy.release.set()
            self.due(job_id)
            self.service.run_once()
            self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)
            self.assert_object_missing()

    def test_I13_delete_succeeded_but_connection_lost_replays_idempotently(self):
        with S3FaultProxy(settings.STORAGE_ENDPOINT_URL) as proxy, patch.object(settings, "STORAGE_ENDPOINT_URL", proxy.endpoint):
            job_id = self.queue_delete()
            proxy.faults.append("lost-response")
            self.service.run_once()
            self.assertTrue(proxy.deleted.is_set(), "Real MinIO never confirmed deletion at proxy")
            self.assert_object_missing()
            self.assertEqual(self.job(job_id).status, CleanupStatus.RETRY)
            self.due(job_id)
            self.service.run_once()
            self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)

    def test_I14_process_crash_after_real_delete_before_done_is_recovered(self):
        job_id = self.queue_delete()
        result = self.fault_process("delete_before_done", job_id)
        self.assertEqual(result.returncode, 75)
        self.assert_object_missing()
        self.assertEqual(self.job(job_id).status, CleanupStatus.PROCESSING)
        self.expire(job_id)
        self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)
        self.assertEqual(self.job(job_id).attempts, 2)

    def test_I19_actual_s3_access_denied_is_blocked(self):
        job_id = self.queue_delete()
        with patch.object(settings, "STORAGE_SECRET_ACCESS_KEY", "wrong-test-only-secret"):
            self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.BLOCKED)
        self.assertEqual(self.job(job_id).last_error_code, "access_denied")
        self.assert_object_present()

    def test_I19_missing_bucket_is_blocked_and_not_generic_404_success(self):
        job_id = self.queue_delete()
        self.storage.client.delete_object(Bucket=self.storage.bucket, Key=self.key)
        self.storage.client.delete_bucket(Bucket=self.storage.bucket)
        # Teardown recreates only this test's already-empty bucket.
        self.addCleanup(self.storage.client.create_bucket, Bucket=self.storage.bucket)
        self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.BLOCKED)
        self.assertNotEqual(self.job(job_id).status, CleanupStatus.DONE)

    def test_I22_versioned_bucket_is_blocked_without_delete_marker_or_purge_claim(self):
        self.storage.client.put_bucket_versioning(Bucket=self.storage.bucket, VersioningConfiguration={"Status": "Enabled"})
        self.storage.save(self.key, b"M2 real S3 payload", "text/plain")
        before = self.storage.client.list_object_versions(Bucket=self.storage.bucket)
        job_id = self.queue_delete()
        self.service.run_once()
        job = self.job(job_id)
        self.assertEqual(job.status, CleanupStatus.BLOCKED)
        self.assertEqual(job.last_error_code, "versioning_unsupported")
        after = self.storage.client.list_object_versions(Bucket=self.storage.bucket)
        self.assertEqual(len(after.get("Versions", [])), len(before.get("Versions", [])))
        self.assertEqual(after.get("DeleteMarkers", []), [])
        self.assert_object_present()

    def test_I22_each_locator_component_mismatch_is_blocked_without_remapping(self):
        job_id = self.queue_delete()
        for column, value in (("storage_backend", "local"), ("storage_target_identity", "http://wrong.invalid"),
                              ("storage_bucket_or_root", "other-bucket"), ("object_key_or_location", "https://wrong.invalid/signed?secret=value")):
            with self.subTest(column=column):
                with self.engine.begin() as connection:
                    original = connection.scalar(text(f"SELECT {column} FROM storage_cleanup_jobs WHERE id=:id"), {"id": job_id})
                    connection.execute(text(f"UPDATE storage_cleanup_jobs SET {column}=:value, status='pending' WHERE id=:id"), {"value": value, "id": job_id})
                self.service.run_once()
                self.assertEqual(self.job(job_id).status, CleanupStatus.BLOCKED)
                self.assert_object_present()
                with self.engine.begin() as connection:
                    connection.execute(text(f"UPDATE storage_cleanup_jobs SET {column}=:value WHERE id=:id"), {"value": original, "id": job_id})

    def test_I24_live_shared_object_blocks_physical_s3_delete(self):
        from app.models.document import Document
        job_id = self.queue_delete()
        with self.sessions() as db:
            db.add(Document(title="Live reference", file_path=self.key, file_type="txt", uploaded_by=self.actor.id))
            db.commit()
        self.service.run_once()
        self.assertEqual(self.job(job_id).last_error_code, "shared_object_reference")
        self.assertEqual(self.job(job_id).status, CleanupStatus.BLOCKED)
        self.assert_object_present()
