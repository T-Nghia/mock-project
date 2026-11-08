"""Run with the dedicated Redis container stopped and no Celery process alive."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import redis

from app.core.config import settings
from app.models.storage_cleanup import CleanupStatus
from tests.integration.test_storage_reliability import S3ReliabilityDatabaseCase


@unittest.skipUnless(os.getenv("RUN_BROKER_DOWN_INTEGRATION") == "1",
                     "Requires explicitly stopped disposable Redis/Celery fixture")
class CleanupIndependenceTestCase(S3ReliabilityDatabaseCase):
    def test_I17_independent_entrypoint_cleans_object_with_redis_and_celery_down(self):
        client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=0.2, socket_connect_timeout=0.2)
        self.addCleanup(client.close)
        with self.assertRaises((redis.ConnectionError, redis.TimeoutError)):
            client.ping()
        job_id = self.queue_delete()
        env = {**self.child_environment(), "CLEANUP_POLL_SECONDS": "0.1"}
        with tempfile.TemporaryDirectory(prefix="m2-independent-") as directory:
            with (Path(directory) / "worker.log").open("w+") as logs:
                worker = subprocess.Popen(
                    [sys.executable, "-m", "app.cleanup_worker"], env=env,
                    cwd=Path(__file__).resolve().parents[2], stdout=logs, stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 20
                    while self.job(job_id).status != CleanupStatus.DONE:
                        self.assertIsNone(worker.poll(), "Independent cleanup worker exited before completion")
                        if time.monotonic() >= deadline:
                            self.fail("Independent cleanup worker did not finish while Redis was down")
                        time.sleep(0.02)
                    self.assert_object_missing()
                finally:
                    if worker.poll() is None:
                        worker.terminate()
                    worker.wait(20)
                self.assertEqual(worker.returncode, 0, "Cleanup did not shut down gracefully")
                logs.seek(0)
                contents = logs.read()
                self.assertIn("event=cleanup_outcome", contents)
                self.assertFalse(settings.STORAGE_SECRET_ACCESS_KEY in contents, "Credential leaked in worker logs")
