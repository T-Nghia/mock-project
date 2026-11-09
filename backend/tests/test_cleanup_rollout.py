from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cleanup_health import healthy
from app.cleanup_worker import run_worker
from app.core.config import Settings, settings
from app.core.maintenance import DocumentMaintenanceMiddleware
from app.services.storage import StorageSafetyError
from app.storage_certification import require_certificate, require_worker_enabled
from tests.cleanup_fixture import certificate_fixture


class CleanupRolloutTestCase(unittest.TestCase):
    def setUp(self):
        config = patch.multiple(settings, STORAGE_BACKEND="s3", STORAGE_BUCKET="isolated-test-bucket",
                                STORAGE_ENDPOINT_URL="http://127.0.0.1:19000", STORAGE_REGION="us-east-1",
                                DOCUMENT_DELETE_ENABLED=False, DOCUMENT_MUTATIONS_ENABLED=True, CLEANUP_ENABLED=False)
        config.start()
        self.addCleanup(config.stop)
        self.certificate = certificate_fixture(self)
        cert = patch.object(settings, "CLEANUP_CERTIFICATE_FILE", self.certificate)
        cert.start()
        self.addCleanup(cert.stop)
        self.app = FastAPI()
        self.app.add_middleware(DocumentMaintenanceMiddleware)
        self.calls = []

        @self.app.delete("/documents/{document_id}")
        def legacy_delete(document_id: str):
            self.calls.append(document_id)
            return {"legacy": True}

        @self.app.get("/documents/{document_id}")
        def read_document(document_id: str):
            return {"id": document_id}

        @self.app.post("/documents/upload")
        def upload():
            self.calls.append("upload")
            return {}

        @self.app.delete("/documents/{document_id}/bookmark")
        def remove_bookmark(document_id: str):
            return {"removed": True}

        self.client = TestClient(self.app)

    def test_default_gate_protects_even_legacy_route_without_mutation(self):
        response = self.client.delete("/documents/legacy-object")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["Retry-After"], "300")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.client.get("/documents/existing").status_code, 200)

    def test_production_configuration_errors_do_not_render_credential_inputs(self):
        sentinel = "unit-only-sensitive-key"
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError) as raised:
            Settings(_env_file=None, ENV="production", JWT_SECRET_KEY=sentinel)
        self.assertNotIn(sentinel, str(raised.exception))
        self.assertNotIn("input_value", str(raised.exception))

    def test_delete_gate_does_not_require_running_worker(self):
        with patch.object(settings, "DOCUMENT_DELETE_ENABLED", True):
            self.assertFalse(settings.CLEANUP_ENABLED)
            self.assertEqual(self.client.delete("/documents/object").status_code, 200)
        self.assertEqual(self.calls, ["object"])

    def test_delete_gate_does_not_block_unrelated_nested_delete_routes(self):
        self.assertEqual(self.client.delete("/documents/object/bookmark").status_code, 200)

    def test_local_rollout_blocked_with_missing_root_or_existing_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "uploads"
            for exists in (False, True):
                if exists:
                    root.mkdir()
                with patch.multiple(settings, DOCUMENT_DELETE_ENABLED=True, CLEANUP_ENABLED=True,
                                    STORAGE_BACKEND="local", UPLOAD_DIR=str(root)):
                    self.assertEqual(self.client.delete("/documents/object").status_code, 503)
                    with self.assertRaisesRegex(StorageSafetyError, "local_cleanup_not_certified"):
                        require_worker_enabled()
        self.assertEqual(self.calls, [])

    def test_missing_mismatched_and_expired_certificate_fail_closed(self):
        original = Path(self.certificate).read_text(encoding="utf-8")
        for change in ("missing", "wrong-target", "expired", "future", "malformed"):
            with self.subTest(change=change):
                certificate = json.loads(original)
                if change == "missing":
                    Path(self.certificate).unlink(missing_ok=True)
                else:
                    if change == "wrong-target":
                        certificate["target_sha256"] = "wrong"
                    if change in {"expired", "future"}:
                        days = -2 if change == "expired" else 2
                        certificate["certified_at"] = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
                    Path(self.certificate).write_text("null" if change == "malformed" else json.dumps(certificate), encoding="utf-8")
                with patch.object(settings, "DOCUMENT_DELETE_ENABLED", True):
                    self.assertEqual(self.client.delete("/documents/object").status_code, 503)
                Path(self.certificate).write_text(original, encoding="utf-8")
        self.assertEqual(self.calls, [])

    def test_worker_disabled_or_changed_principal_is_rejected(self):
        with self.assertRaisesRegex(StorageSafetyError, "cleanup_disabled"):
            require_worker_enabled()
        with patch.multiple(settings, CLEANUP_ENABLED=True, STORAGE_ACCESS_KEY_ID="different-worker"):
            with self.assertRaisesRegex(StorageSafetyError, "target_uncertified"):
                require_worker_enabled()
        require_certificate()  # API principal may differ; target must still match.

    def test_mutation_gate_blocks_upload_and_delete_but_not_reads(self):
        with patch.object(settings, "DOCUMENT_MUTATIONS_ENABLED", False):
            self.assertEqual(self.client.post("/documents/upload").status_code, 503)
            self.assertEqual(self.client.delete("/documents/object").status_code, 503)
            self.assertEqual(self.client.get("/documents/object").status_code, 200)
        self.assertEqual(self.calls, [])

    def test_health_uses_local_heartbeat_without_broker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "heartbeat"
            with patch.object(settings, "CLEANUP_HEARTBEAT_FILE", str(path)):
                self.assertFalse(healthy())
                path.touch()
                self.assertTrue(healthy())
                future = time.time() + 3600
                os.utime(path, (future, future))
                self.assertFalse(healthy())
                past = time.time() - 3600
                os.utime(path, (past, past))
                self.assertFalse(healthy())

    def test_shutdown_drains_active_cycle_before_exiting_without_another_claim(self):
        stop, entered, release = threading.Event(), threading.Event(), threading.Event()
        service = Mock()

        def cycle():
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test barrier timed out")

        service.run_once.side_effect = cycle
        thread = threading.Thread(target=run_worker, args=(service, stop))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            stop.set()
            self.assertTrue(thread.is_alive(), "An active external call cannot be declared drained")
            self.assertEqual(service.run_once.call_count, 1)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(service.run_once.call_count, 1)

    def test_revoked_certificate_before_poll_prevents_any_claim_and_logs_no_secret(self):
        stop, service = threading.Event(), Mock()

        def validator():
            stop.set()
            raise RuntimeError("never-log-certificate-secret")

        with self.assertLogs("app.cleanup_worker", level="ERROR") as logs:
            run_worker(service, stop, validator=validator)
        service.run_once.assert_not_called()
        self.assertNotIn("never-log-certificate-secret", " ".join(logs.output))
