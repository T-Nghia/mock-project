"""SIGKILL a real prefork child; Redis redelivers the production processing task."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from app.models.document import Document, DocumentChunk
from app.tasks.document_processing import process_document
from tests.integration.test_storage_reliability import S3ReliabilityDatabaseCase


@unittest.skipUnless(os.getenv("RUN_CELERY_INTEGRATION") == "1" and os.name == "posix",
                     "Real prefork/Redis redelivery requires opt-in Linux fixture")
class CeleryRedeliveryTestCase(S3ReliabilityDatabaseCase):
    def test_I16_actual_prefork_child_loss_redelivers_after_delete_without_writes(self):
        self.assertFalse(process_document.app.conf.task_always_eager)
        with tempfile.TemporaryDirectory(prefix="m2-celery-") as directory:
            directory = Path(directory)
            queue = "m2-" + uuid.uuid4().hex
            with (directory / "worker.log").open("w+") as logs:
                worker = subprocess.Popen(
                    [sys.executable, "-m", "tests.integration.celery_fault_worker", str(directory), queue],
                    cwd=Path(__file__).resolve().parents[2], env=self.child_environment(),
                    stdout=logs, stderr=subprocess.STDOUT, start_new_session=True,
                )

                def wait_for(pattern, predicate=lambda _: True):
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        self.assertIsNone(worker.poll(), "Real Celery worker exited early")
                        for path in directory.glob(pattern):
                            value = json.loads(path.read_text())
                            if predicate(value):
                                return value
                        time.sleep(0.02)
                    self.fail("Real Celery did not reach synchronized marker " + pattern)

                try:
                    wait_for("ready-*.json")
                    task = process_document.apply_async(args=[str(self.document_id)], queue=queue)
                    started = wait_for("embedding-*.json", lambda value: value["task_id"] == task.id)
                    self.assertNotIn(started["pid"], {os.getpid(), worker.pid})
                    self.queue_delete()
                    # Kill only the verified prefork child paused by our marker.
                    os.kill(started["pid"], signal.SIGKILL)
                    redelivery = wait_for("delivery-*.json", lambda value: value["task_id"] == task.id and value["redelivered"])
                    self.assertNotEqual(redelivery["pid"], started["pid"])
                    result = wait_for("complete-*.json", lambda value: value["task_id"] == task.id and value["state"] == "SUCCESS")
                    self.assertEqual(result["outcome"], "document_deleted")
                    self.assertEqual(self.count(Document), 0)
                    self.assertEqual(self.count(DocumentChunk), 0)
                    self.assert_object_present()  # Processing does not perform physical cleanup.
                finally:
                    (directory / "release").touch()
                    if worker.poll() is None:
                        os.killpg(worker.pid, signal.SIGTERM)
                        try:
                            worker.wait(15)
                        except subprocess.TimeoutExpired:
                            os.killpg(worker.pid, signal.SIGKILL)
                            worker.wait(5)
