"""Real S3 snapshot/restore; separate opt-in Docker PostgreSQL dump drill."""
from datetime import datetime, timezone
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

from botocore.exceptions import ClientError
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.document import Document
from app.models.storage_cleanup import CleanupStatus, StorageCleanupJob
from app.repositories.storage_cleanup_repo import StorageCleanupJobRepository
from app.services.storage import S3Storage, StorageSafetyError
from app.services.storage_cleanup_service import validate_claim_target
from app.storage_backup import export_objects, restore_objects, verify_live_references
from app.storage_certification import target_fingerprint
from app.cleanup_worker import validate_startup
from tests.integration.s3_fault_proxy import S3FaultProxy
from tests.integration.test_storage_reliability import S3ReliabilityDatabaseCase


class BackupFixture(S3ReliabilityDatabaseCase):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory(prefix="m3-backup-")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        paused = patch.multiple(settings, DOCUMENT_DELETE_ENABLED=False, DOCUMENT_MUTATIONS_ENABLED=False, CLEANUP_ENABLED=False)
        paused.start()
        self.addCleanup(paused.stop)
        self.restored_bucket = "slrms-restore-verify-" + uuid.uuid4().hex
        self.addCleanup(self.remove_restored_bucket)

    def remove_restored_bucket(self):
        try:
            rows = self.storage.client.list_objects_v2(Bucket=self.restored_bucket)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchBucket":
                return
            raise
        self.assertRegex(self.restored_bucket, r"^slrms-restore-verify-[0-9a-f]{32}$")
        for row in rows.get("Contents", []):
            self.storage.client.delete_object(Bucket=self.restored_bucket, Key=row["Key"])
        self.storage.client.delete_bucket(Bucket=self.restored_bucket)

    def evidence(self):
        path = self.directory / "quiescence.json"
        path.write_text(json.dumps({"target_sha256": target_fingerprint(), "verified_at": datetime.now(timezone.utc).isoformat(),
                                    "ticket": "DISPOSABLE-DRILL", "all_writers_stopped": True,
                                    "storage_requests_drained": True, "delete_fence_enforced": True}), encoding="utf-8")
        return path

    def snapshot(self):
        destination = self.directory / "storage"
        export_objects(destination, revision="26050faee3486fd2d9c93d6df163c4e1e4bb5694", evidence_file=self.evidence())
        return destination


@unittest.skipUnless(os.getenv("RUN_RELIABILITY_INTEGRATION") == "1", "Requires real MinIO/PostgreSQL")
class StorageBackupTestCase(BackupFixture):
    def test_snapshot_with_controlled_delete_fence_restores_bytes_and_metadata(self):
        self.storage.client.put_object(Bucket=self.storage.bucket, Key=self.key, Body=b"M2 real S3 payload",
                                       ContentType="text/plain", Metadata={"lesson": "retained"})
        with S3FaultProxy(settings.STORAGE_ENDPOINT_URL) as proxy, patch.object(settings, "STORAGE_ENDPOINT_URL", proxy.endpoint):
            proxy.deny_deletes = True
            guarded = S3Storage(cleanup=True)
            try:
                with self.assertRaises(ClientError) as denied:
                    guarded.delete(self.key)
                self.assertEqual(denied.exception.response["ResponseMetadata"]["HTTPStatusCode"], 403)
                destination = self.snapshot()
            finally:
                guarded.client.close()
        restore_objects(destination, self.restored_bucket)
        restored = self.storage.client.get_object(Bucket=self.restored_bucket, Key=self.key)
        self.assertEqual(restored["Body"].read(), b"M2 real S3 payload")
        self.assertEqual(restored["Metadata"], {"lesson": "retained"})
        self.assert_object_present()
        with self.assertRaisesRegex(StorageSafetyError, "already_exists"):
            restore_objects(destination, self.restored_bucket)

    def test_backup_gate_and_invalid_quiescence_fail_before_creating_snapshot(self):
        for flag in ("DOCUMENT_DELETE_ENABLED", "DOCUMENT_MUTATIONS_ENABLED", "CLEANUP_ENABLED"):
            with patch.object(settings, flag, True), self.assertRaisesRegex(StorageSafetyError, "closed_gates"):
                self.snapshot()
        evidence = self.evidence()
        data = json.loads(evidence.read_text(encoding="utf-8"))
        data["storage_requests_drained"] = False
        evidence.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(StorageSafetyError, "quiescence_unverified"):
            export_objects(self.directory / "storage", revision="a" * 40, evidence_file=evidence)
        self.assertFalse((self.directory / "storage").exists())
        self.assert_object_present()

    def test_corrupted_snapshot_refused_before_restore_target_creation(self):
        destination = self.snapshot()
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        (destination / manifest["objects"][0]["file"]).write_bytes(b"corrupted")
        with self.assertRaisesRegex(StorageSafetyError, "checksum_mismatch"):
            restore_objects(destination, self.restored_bucket)
        with self.assertRaises(ClientError):
            self.storage.client.head_bucket(Bucket=self.restored_bucket)

    def test_reference_verification_reports_missing_objects_and_keeps_gates_closed(self):
        self.assertEqual(verify_live_references(self.sessions)["verified_live_documents"], 1)
        self.storage.client.delete_object(Bucket=self.storage.bucket, Key=self.key)
        with self.assertRaises(ClientError):
            verify_live_references(self.sessions)
        self.assertFalse(settings.CLEANUP_ENABLED)

    def test_restore_verification_closes_read_transactions_before_real_s3_io(self):
        sessions = []
        calls = []
        guarded = S3Storage(cleanup=True)

        def factory():
            db = self.sessions()
            sessions.append(db)
            return db

        def assert_closed(**_):
            self.assertTrue(sessions)
            self.assertTrue(all(not db.in_transaction() for db in sessions))
            calls.append("real-head-object")

        guarded.client.meta.events.register("before-call.s3.HeadObject", assert_closed)
        with patch("app.storage_backup.S3Storage", return_value=guarded):
            self.assertEqual(verify_live_references(factory)["verified_live_documents"], 1)
        self.assertEqual(calls, ["real-head-object"])


@unittest.skipUnless(os.getenv("PG_TEST_CONTAINER") and os.getenv("RUN_RELIABILITY_INTEGRATION") == "1",
                     "Dedicated Docker PostgreSQL ID required for real dump/restore drill")
class PostgreSQLBackupDrillTestCase(BackupFixture):
    def pg(self, *args, input=None):
        return subprocess.run(["docker", "exec", "-i", os.environ["PG_TEST_CONTAINER"], *args],
                              input=input, capture_output=True, check=True, timeout=60).stdout

    def test_I23_real_pg_dump_restore_preserves_queue_and_never_remaps_target(self):
        job_id = self.queue_delete()
        for state in (CleanupStatus.PROCESSING, CleanupStatus.BLOCKED):
            key = uuid.uuid4().hex + ".txt"
            self.storage.save(key, b"retained queued object", "text/plain")
            with self.sessions() as db:
                document = Document(title="Queued", file_path=key, file_type="txt", uploaded_by=self.actor.id)
                db.add(document)
                db.commit()
                document_id = document.id
            extra_job = self.queue_delete(document_id)
            with self.sessions() as db:
                row = db.get(StorageCleanupJob, extra_job)
                row.status = state
                if state == CleanupStatus.PROCESSING:
                    row.lease_token = uuid.uuid4()
                    row.lease_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                db.commit()
        live_key = uuid.uuid4().hex + ".txt"
        self.storage.save(live_key, b"live restored object", "text/plain")
        with self.sessions() as db:
            db.add(Document(title="Live", file_path=live_key, file_type="txt", uploaded_by=self.actor.id))
            db.commit()
        destination = self.snapshot()
        with self.sessions() as db:
            original = {row.id: (row.status, row.storage_target_identity, row.storage_bucket_or_root,
                                 row.object_key_or_location, row.lease_token, row.lease_expires_at)
                        for row in db.scalars(select(StorageCleanupJob))}
        url = make_url(self.database_url)
        restored_db = "slrms_restore_verify_" + uuid.uuid4().hex
        # Only this uniquely-created disposable database is eligible for teardown.
        self.pg("createdb", "-U", url.username, restored_db)
        try:
            dump = self.pg("pg_dump", "-U", url.username, "-d", url.database, "--format=custom", "--no-owner", "--no-acl")
            self.assertGreater(len(dump), 0)
            self.pg("pg_restore", "-U", url.username, "-d", restored_db, "--no-owner", "--no-acl", input=dump)
            engine = create_engine(url.set(database=restored_db),
                                   connect_args={"options": f"-csearch_path={self.schema},public"})
            try:
                sessions = sessionmaker(bind=engine, autoflush=False)
                with S3FaultProxy(settings.STORAGE_ENDPOINT_URL) as proxy, patch.multiple(
                    settings, STORAGE_BUCKET=self.restored_bucket, STORAGE_ENDPOINT_URL=proxy.endpoint,
                ):
                    proxy.forbidden_buckets.add(self.storage.bucket)
                    restore_objects(destination, self.restored_bucket)
                    self.assertEqual(verify_live_references(sessions)["verified_live_documents"], 1)
                    with self.assertRaisesRegex(StorageSafetyError, "cleanup_disabled"):
                        validate_startup(sessions)
                    with sessions() as db:
                        job = db.get(StorageCleanupJob, job_id)
                        self.assertEqual(job.storage_bucket_or_root, self.storage.bucket)
                        restored = {row.id: (row.status, row.storage_target_identity, row.storage_bucket_or_root,
                                             row.object_key_or_location, row.lease_token, row.lease_expires_at)
                                    for row in db.scalars(select(StorageCleanupJob))}
                        self.assertEqual(restored, original)
                        self.assertEqual({entry[0] for entry in restored.values()},
                                         {CleanupStatus.PENDING, CleanupStatus.PROCESSING, CleanupStatus.BLOCKED})
                        claim = StorageCleanupJobRepository(db).claim(120)
                        with self.assertRaisesRegex(StorageSafetyError, "target_mismatch"):
                            validate_claim_target(claim)
                        db.rollback()
                        self.assertEqual(db.get(StorageCleanupJob, job_id).status, CleanupStatus.PENDING)
                    self.assertEqual(proxy.forbidden_requests, [], "Restore/verify must never even attempt the original bucket")
            finally:
                engine.dispose()
            self.assertFalse(settings.CLEANUP_ENABLED)
        finally:
            self.assertRegex(restored_db, r"^slrms_restore_verify_[0-9a-f]{32}$")
            self.pg("dropdb", "-U", url.username, restored_db)
