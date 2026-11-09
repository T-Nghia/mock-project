"""Real S3 certification, maintenance gate, and API-to-worker acceptance."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from fastapi.testclient import TestClient

from app.cleanup_worker import validate_startup
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.storage_cleanup import CleanupStatus, StorageCleanupJob
from app.models.document import Document
from app.models.user import User, UserRole
from app.services.storage import StorageSafetyError
from app.storage_certification import certify_target
from tests.integration.test_storage_reliability import S3ReliabilityDatabaseCase


@unittest.skipUnless(os.getenv("RUN_RELIABILITY_INTEGRATION") == "1", "Requires real PostgreSQL and MinIO")
class CleanupRolloutPostgreSQLTestCase(S3ReliabilityDatabaseCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory(prefix="m3-cert-")
        self.addCleanup(self.temp.cleanup)
        self.certificate = Path(self.temp.name) / "target.json"
        self.certificate.write_text(json.dumps(certify_target()), encoding="utf-8")
        self.gate = patch.multiple(settings, CLEANUP_CERTIFICATE_FILE=str(self.certificate),
                                   DOCUMENT_DELETE_ENABLED=True, CLEANUP_ENABLED=False)
        self.gate.start()
        self.addCleanup(self.gate.stop)
        previous = app.dependency_overrides.get(get_db)

        def database():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None) if previous is None
                        else app.dependency_overrides.update({get_db: previous}))
        self.headers = {"Authorization": "Bearer " + create_access_token(str(self.actor.id), "teacher")}
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_real_api_delete_queues_while_worker_disabled_then_cleans_when_enabled(self):
        with self.assertRaisesRegex(StorageSafetyError, "cleanup_disabled"):
            validate_startup(self.sessions)
        response = self.client.delete(f"/documents/{self.document_id}", headers=self.headers)
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.count(StorageCleanupJob), 1)
        self.assert_object_present()
        self.assertEqual(self.client.delete(f"/documents/{self.document_id}", headers=self.headers).status_code, 404)
        self.assertEqual(self.count(StorageCleanupJob), 1)
        with patch.object(settings, "CLEANUP_ENABLED", True):
            validate_startup(self.sessions)
            self.service.run_once()
        self.assertEqual(self.job(self.only_job_id()).status, CleanupStatus.DONE)
        self.assert_object_missing()

    def only_job_id(self):
        from sqlalchemy import select
        with self.sessions() as db:
            return db.scalar(select(StorageCleanupJob.id))

    def test_disabled_gate_preserves_metadata_object_and_zero_jobs(self):
        with patch.object(settings, "DOCUMENT_DELETE_ENABLED", False):
            response = self.client.delete(f"/documents/{self.document_id}", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertIn("Retry-After", response.headers)
        self.assertEqual(self.count(StorageCleanupJob), 0)
        self.assertEqual(self.client.get(f"/documents/{self.document_id}", headers=self.headers).status_code, 200)
        self.assert_object_present()

    def test_uncertified_or_wrong_target_blocks_without_metadata_change(self):
        self.certificate.write_text('{"status":"UNVERIFIED"}', encoding="utf-8")
        self.assertEqual(self.client.delete(f"/documents/{self.document_id}", headers=self.headers).status_code, 503)
        self.assertEqual(self.count(StorageCleanupJob), 0)
        self.assert_object_present()

    def test_versioned_target_cannot_be_certified(self):
        self.storage.client.put_bucket_versioning(Bucket=self.storage.bucket, VersioningConfiguration={"Status": "Enabled"})
        with self.assertRaisesRegex(StorageSafetyError, "versioning_unsupported"):
            certify_target()
        self.assert_object_present()

    def test_local_root_replacement_blocks_api_and_worker_before_any_claim(self):
        root = Path(self.temp.name) / "uploads"
        root.mkdir()
        path = root / self.key
        path.write_text("backing object must survive")
        with self.sessions() as db:
            db.get(Document, self.document_id).file_path = str(path)
            db.commit()
        with patch.multiple(settings, STORAGE_BACKEND="local", UPLOAD_DIR=str(root), CLEANUP_ENABLED=True):
            # Historical local intent may predate M3. It must remain pending.
            job_id = self.queue_delete()
            offline = root.parent / "offline-backing"
            root.rename(offline)
            root.mkdir()
            self.assertTrue(root.is_dir())
            with self.assertRaisesRegex(StorageSafetyError, "local_cleanup_not_certified"):
                validate_startup(self.sessions)
            self.assertEqual(self.client.delete(f"/documents/{self.document_id}", headers=self.headers).status_code, 503)
            self.assertEqual(self.job(job_id).status, CleanupStatus.PENDING)
            self.assertEqual(self.job(job_id).attempts, 0)
            self.assertIsNone(self.job(job_id).completed_at)
            self.assertEqual((offline / self.key).read_text(), "backing object must survive")

    def test_api_auth_uuid_and_ownership_still_enforced_with_open_gate(self):
        self.assertEqual(self.client.delete(f"/documents/{self.document_id}").status_code, 401)
        self.assertEqual(self.client.delete("/documents/not-a-uuid", headers=self.headers).status_code, 422)
        for role in (UserRole.STUDENT, UserRole.TEACHER):
            with self.sessions() as db:
                other = User(full_name="Other", email=role.value + "@example.com", hashed_password="unused", role=role)
                db.add(other)
                db.commit()
                token = create_access_token(str(other.id), role.value)
            self.assertEqual(self.client.delete(f"/documents/{self.document_id}",
                                               headers={"Authorization": "Bearer " + token}).status_code, 403)
        self.assertEqual(self.count(StorageCleanupJob), 0)
        self.assert_object_present()

    def test_I09_database_insert_or_delete_failure_preserves_real_storage(self):
        for table, operation in (("storage_cleanup_jobs", "INSERT"), ("documents", "DELETE")):
            with self.subTest(table=table):
                with self.engine.begin() as connection:
                    connection.execute(text(f'CREATE FUNCTION "{self.schema}".reject_write() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION \'Controlled M3 write failure\'; END; $$'))
                    connection.execute(text(f'CREATE TRIGGER reject_write BEFORE {operation} ON "{self.schema}".{table} FOR EACH ROW EXECUTE FUNCTION "{self.schema}".reject_write()'))
                try:
                    response = self.client.delete(f"/documents/{self.document_id}", headers=self.headers)
                    self.assertEqual(response.status_code, 500)
                    self.assertEqual(self.count(StorageCleanupJob), 0)
                    self.assertEqual(self.client.get(f"/documents/{self.document_id}", headers=self.headers).status_code, 200)
                    self.assert_object_present()
                finally:
                    with self.engine.begin() as connection:
                        connection.execute(text(f'DROP TRIGGER reject_write ON "{self.schema}".{table}'))
                        connection.execute(text(f'DROP FUNCTION "{self.schema}".reject_write()'))

    def test_unknown_commit_ack_after_real_postgresql_commit_is_500_with_durable_intent(self):
        previous = app.dependency_overrides[get_db]

        def lost_ack_database():
            with self.sessions() as db:
                commit = db.commit

                def lose_ack():
                    commit()  # Real PostgreSQL commit, not an unflushed/mock write.
                    raise OperationalError("COMMIT", None, RuntimeError("controlled acknowledgement loss"))

                with patch.object(db, "commit", side_effect=lose_ack):
                    yield db

        app.dependency_overrides[get_db] = lost_ack_database
        try:
            response = self.client.delete(f"/documents/{self.document_id}", headers=self.headers)
            self.assertEqual(response.status_code, 500)
        finally:
            app.dependency_overrides[get_db] = previous
        with self.sessions() as db:
            self.assertIsNone(db.get(Document, self.document_id))
        self.assertEqual(self.count(StorageCleanupJob), 1)
        self.assertEqual(self.job(self.only_job_id()).status, CleanupStatus.PENDING)
        self.assert_object_present()
        self.service.run_once()
        self.assertEqual(self.job(self.only_job_id()).status, CleanupStatus.DONE)
        self.assert_object_missing()
