"""Actual Linux filesystem safety and PostgreSQL cleanup outcomes."""

import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.models.document import Document
from app.models.storage_cleanup import CleanupStatus
from app.services.storage import LocalStorage
from app.services.storage_cleanup_service import StorageCleanupService
from tests.integration.reliability_support import ReliabilityDatabaseCase


class LocalReliabilityDatabaseCase(ReliabilityDatabaseCase):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory(prefix="m2-local-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "uploads"
        self.root.mkdir()
        self.local_settings = patch.multiple(settings, STORAGE_BACKEND="local", UPLOAD_DIR=str(self.root))
        self.local_settings.start()
        self.addCleanup(self.local_settings.stop)
        self.path = self.root / self.key
        self.path.write_text("keep local payload")
        with self.sessions() as db:
            db.get(Document, self.document_id).file_path = str(self.path)
            db.commit()


@unittest.skipUnless(os.getenv("CLEANUP_TEST_DATABASE_URL"), "Requires dedicated PostgreSQL fixture")
class LocalRootAvailabilityTestCase(LocalReliabilityDatabaseCase):
    def test_missing_root_retries_without_done_then_recovers(self):
        job_id = self.queue_delete()
        offline = self.root.parent / "offline-backing"
        self.assertEqual(offline.parent.resolve(), self.root.parent.resolve())
        self.root.rename(offline)
        try:
            self.service.run_once()
            self.assertEqual(self.job(job_id).status, CleanupStatus.RETRY)
            self.assertIsNone(self.job(job_id).completed_at)
            self.assertEqual((offline / self.key).read_text(), "keep local payload")
        finally:
            offline.rename(self.root)
        self.due(job_id)
        self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)
        self.assertFalse(self.path.exists())

    def test_missing_intermediate_under_accessible_root_is_done(self):
        nested = self.root / "nested"
        nested.mkdir()
        target = nested / self.key
        self.path.rename(target)
        with self.sessions() as db:
            db.get(Document, self.document_id).file_path = str(target)
            db.commit()
        job_id = self.queue_delete()
        target.unlink()
        nested.rmdir()
        self.assertTrue(self.root.is_dir())
        self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)

    def test_existing_root_backing_io_failure_retries_and_keeps_object(self):
        job_id = self.queue_delete()
        self.assertTrue(self.root.is_dir())
        target = "app.services.storage._windows_directory_guards" if os.name == "nt" else "app.services.storage.os.open"
        with patch(target, side_effect=OSError(errno.EIO, "injected unavailable backing filesystem")):
            self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.RETRY)
        self.assertIsNone(self.job(job_id).completed_at)
        self.assertTrue(self.path.exists())
        self.due(job_id)
        self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)

    def test_locator_resolution_io_failure_is_retryable_not_invalid_target(self):
        job_id = self.queue_delete()
        with patch("app.services.storage_cleanup_service.snapshot_storage_locator",
                   side_effect=OSError(errno.EIO, "backing filesystem unavailable during resolution")):
            self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.RETRY)
        self.assertIsNone(self.job(job_id).completed_at)
        self.assertTrue(self.path.exists())


@unittest.skipUnless(os.getenv("CLEANUP_TEST_DATABASE_URL") and os.name == "posix",
                     "Actual POSIX filesystem/dir_fd evidence requires Linux PostgreSQL fixture")
class LocalReliabilityTestCase(LocalReliabilityDatabaseCase):
    def test_local_cleanup_and_missing_object_are_idempotent(self):
        job_id = self.queue_delete()
        self.path.unlink()
        self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)
        LocalStorage().delete(str(self.path))

    def test_I21_actual_permission_error_is_blocked_not_done(self):
        job_id = self.queue_delete()

        class UnprivilegedStorage(LocalStorage):
            def delete(storage, location):
                # CI may be root; temporarily drop only for this synchronous OS call.
                previous = os.geteuid()
                if previous == 0:
                    os.seteuid(65534)
                try:
                    super().delete(location)
                finally:
                    if previous == 0:
                        os.seteuid(previous)

        self.root.chmod(0o500)
        try:
            service = StorageCleanupService(self.sessions, storage_factory=lambda **_: UnprivilegedStorage())
            service.run_once()
        finally:
            self.root.chmod(0o700)
        self.assertEqual(self.job(job_id).status, CleanupStatus.BLOCKED)
        self.assertEqual(self.job(job_id).last_error_code, "permission_denied")
        self.assertTrue(self.path.exists())

    def test_I21_injected_os_io_error_retries_and_recovers(self):
        job_id = self.queue_delete()
        with patch("app.services.storage.os.unlink", side_effect=OSError(errno.EIO, "injected device failure")):
            self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.RETRY)
        self.assertTrue(self.path.exists())
        self.due(job_id)
        self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.DONE)
        self.assertFalse(self.path.exists())

    def test_queued_object_replaced_with_symlink_cannot_delete_external_file(self):
        job_id = self.queue_delete()
        outside = self.root.parent / "outside.txt"
        outside.write_text("never delete")
        self.path.unlink()
        self.path.symlink_to(outside)
        self.service.run_once()
        self.assertEqual(self.job(job_id).status, CleanupStatus.BLOCKED)
        self.assertEqual(outside.read_text(), "never delete")

    def test_parent_swap_after_validation_cannot_redirect_dir_fd_unlink(self):
        nested = self.root / "nested"
        nested.mkdir()
        original = nested / "target.txt"
        original.write_text("original")
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "target.txt").write_text("never delete")
        real_stat = os.stat
        swapped = False

        def swap_parent(path, *args, **kwargs):
            nonlocal swapped
            result = real_stat(path, *args, **kwargs)
            if kwargs.get("dir_fd") is not None and not swapped:
                nested.rename(self.root / "renamed")
                nested.symlink_to(outside, target_is_directory=True)
                swapped = True
            return result

        with patch("app.services.storage.os.stat", side_effect=swap_parent):
            LocalStorage().delete(str(original))
        self.assertTrue(swapped)
        self.assertFalse((self.root / "renamed" / "target.txt").exists())
        self.assertEqual((outside / "target.txt").read_text(), "never delete")
