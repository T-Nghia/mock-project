import errno
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from app.cleanup_worker import main, run_worker, validate_startup
from app.core.config import settings
from app.models.storage_cleanup import CleanupStatus
from app.services.storage import LocalStorage, S3Storage, StorageSafetyError, get_storage, _windows_directory_guards
from app.services.storage_cleanup_service import classify_cleanup_error, cleanup_retry_delay


def s3_error(code, status):
    return ClientError({"Error": {"Code": code, "Message": "never-log-secret"},
                        "ResponseMetadata": {"HTTPStatusCode": status}}, "DeleteObject")


class LocalDeletionContractTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "uploads"
        self.root.mkdir()
        self.patch = patch.object(settings, "UPLOAD_DIR", str(self.root))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.storage = LocalStorage()

    def test_existing_file_and_missing_file_are_idempotent(self):
        path = self.root / "nested" / "file.txt"
        path.parent.mkdir()
        path.write_text("payload")
        self.storage.delete(str(path))
        self.storage.delete(str(path))
        self.storage.delete(str(self.root / "missing-parent" / "file.txt"))
        self.assertFalse(path.exists())

    def test_outside_root_and_traversal_never_delete(self):
        outside = self.root.parent / "outside.txt"
        outside.write_text("keep")
        for path in (outside, self.root / ".." / "outside.txt", self.root):
            with self.subTest(path=path), self.assertRaises(StorageSafetyError):
                self.storage.delete(str(path))
        self.assertEqual(outside.read_text(), "keep")

    def test_permission_and_io_errors_are_not_swallowed(self):
        path = self.root / "file.txt"
        path.write_text("keep")
        target = "pathlib.Path.unlink" if os.name == "nt" else "app.services.storage.os.unlink"
        for error in (PermissionError(errno.EACCES, "denied"), OSError(errno.EIO, "device error")):
            with self.subTest(error=type(error).__name__), patch(target, side_effect=error):
                with self.assertRaises(type(error)) as raised:
                    self.storage.delete(str(path))
                self.assertIs(raised.exception, error)
        self.assertEqual(path.read_text(), "keep")

    def test_missing_root_is_not_evidence_that_the_object_is_missing(self):
        path = self.root / "file.txt"
        path.write_text("retained on unavailable backing storage")
        offline = self.root.parent / "offline-backing"
        self.assertEqual(offline.parent.resolve(), self.root.parent.resolve())
        self.root.rename(offline)
        try:
            self.assertTrue((offline / path.name).is_file())
            with self.assertRaises(FileNotFoundError):
                self.storage.delete(str(path))
        finally:
            offline.rename(self.root)
        self.assertTrue(path.exists())

    def test_root_open_errors_propagate_even_when_reported_as_not_found(self):
        path = self.root / "file.txt"
        path.write_text("keep")
        for error in (FileNotFoundError(errno.ENOENT, "root unavailable"),
                      PermissionError(errno.EACCES, "root denied"), OSError(errno.EIO, "root I/O")):
            target = "app.services.storage._windows_directory_guards" if os.name == "nt" else "app.services.storage.os.open"
            with self.subTest(error=type(error).__name__), patch(target, side_effect=error):
                with self.assertRaises(type(error)) as raised:
                    self.storage.delete(str(path))
                self.assertIs(raised.exception, error)
        self.assertTrue(path.exists())

    def test_lookup_io_error_with_existing_root_is_not_absence(self):
        path = self.root / "file.txt"
        path.write_text("keep")
        target = "app.services.storage.os.lstat" if os.name == "nt" else "app.services.storage.os.stat"
        original = os.lstat if os.name == "nt" else os.stat
        failure = OSError(errno.EIO, "backing storage unavailable")

        def lookup(value, *args, **kwargs):
            is_target = Path(value) == path if os.name == "nt" else kwargs.get("dir_fd") is not None
            if is_target:
                raise failure
            return original(value, *args, **kwargs)

        with patch(target, side_effect=lookup):
            with self.assertRaises(OSError) as raised:
                self.storage.delete(str(path))
        self.assertIs(raised.exception, failure)
        self.assertTrue(path.exists())

    @unittest.skipIf(os.name == "nt", "Real POSIX symlink and dir_fd evidence runs in Linux suite")
    def test_symlink_file_and_parent_cannot_escape_root(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        file = outside / "keep.txt"
        file.write_text("keep")
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        (self.root / "linked.txt").symlink_to(file)
        for path in (self.root / "linked" / "keep.txt", self.root / "linked.txt"):
            with self.subTest(path=path), self.assertRaises((StorageSafetyError, OSError)):
                self.storage.delete(str(path))
        self.assertEqual(file.read_text(), "keep")


@unittest.skipUnless(os.name == "nt", "Windows handle-sharing evidence runs on Windows")
class WindowsDeletionHandleTestCase(unittest.TestCase):
    def test_network_path_not_found_is_not_a_missing_object(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(settings, "UPLOAD_DIR", directory):
            path = Path(directory).resolve() / "file.txt"
            path.write_text("keep")
            original = os.lstat
            failure = FileNotFoundError(errno.ENOENT, "network unavailable")
            failure.winerror = 53  # ERROR_BAD_NETPATH, distinct from FILE/PATH_NOT_FOUND.

            def lookup(value, *args, **kwargs):
                if Path(value) == path:
                    raise failure
                return original(value, *args, **kwargs)

            with patch("app.services.storage.os.lstat", side_effect=lookup):
                with self.assertRaises(FileNotFoundError):
                    LocalStorage().delete(str(path))
            self.assertTrue(path.exists())

    def test_directory_guards_deny_write_handles_and_rename_until_unlink_finishes(self):
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
        invalid = wintypes.HANDLE(-1).value
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            guarded = parent / "guarded"
            guarded.mkdir()

            def write_handle():
                return create(str(guarded), 0x40000000, 7, None, 3, 0x02200000, None)

            baseline = write_handle()
            self.assertNotEqual(baseline, invalid, "Test owner must be allowed to open a directory for writes")
            close(baseline)
            with _windows_directory_guards(guarded):
                handle = write_handle()
                error = ctypes.get_last_error()
                if handle != invalid:
                    close(handle)
                self.assertEqual(handle, invalid, "A writer could change reparse metadata during deletion")
                self.assertEqual(error, 32)  # ERROR_SHARING_VIOLATION, not an ACL denial.
                target = parent / "renamed"
                try:
                    guarded.rename(target)
                except PermissionError:
                    denied = True
                else:
                    target.rename(guarded)
                    denied = False
                self.assertTrue(denied, "An ancestor could be renamed during deletion")


class S3DeletionContractTestCase(unittest.TestCase):
    def setUp(self):
        self.factory = patch("app.services.storage.boto3.client")
        self.client = self.factory.start().return_value
        self.addCleanup(self.factory.stop)
        self.storage = S3Storage(cleanup=True)

    def test_cleanup_sdk_has_one_attempt_and_bounded_timeouts(self):
        with patch("app.services.storage.boto3.client") as factory:
            S3Storage(cleanup=True)
        config = factory.call_args.kwargs["config"]
        self.assertEqual(config.retries["total_max_attempts"], 1)
        self.assertEqual(config.connect_timeout, 5)
        self.assertEqual(config.read_timeout, 15)

    def test_delete_confirms_bucket_and_only_exact_no_such_key_is_success(self):
        self.client.delete_object.side_effect = s3_error("NoSuchKey", 404)
        self.storage.delete("missing-key")
        self.client.head_bucket.assert_called_once_with(Bucket=self.storage.bucket)
        for code in ("NoSuchBucket", "404", "NotFound", "AccessDenied"):
            with self.subTest(code=code):
                self.client.delete_object.side_effect = s3_error(code, 404)
                with self.assertRaises(ClientError):
                    self.storage.delete("key")

    def test_missing_bucket_is_never_treated_as_missing_object(self):
        self.client.head_bucket.side_effect = s3_error("NoSuchBucket", 404)
        with self.assertRaises(ClientError):
            self.storage.delete("key")
        self.client.delete_object.assert_not_called()

    def test_versioning_and_lock_fail_closed(self):
        for state in ("Enabled", "Suspended", "unknown"):
            self.client.get_bucket_versioning.return_value = {"Status": state}
            with self.subTest(state=state), self.assertRaises(StorageSafetyError):
                self.storage.validate_cleanup_target()
        self.client.get_bucket_versioning.return_value = {}
        self.client.get_object_lock_configuration.return_value = {
            "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"},
        }
        with self.assertRaises(StorageSafetyError):
            self.storage.validate_cleanup_target()
        self.client.delete_object.assert_not_called()

    def test_unversioned_unlocked_bucket_validates_and_unknown_lock_error_does_not(self):
        self.client.get_bucket_versioning.return_value = {}
        self.client.get_object_lock_configuration.side_effect = s3_error("ObjectLockConfigurationNotFoundError", 404)
        self.storage.validate_cleanup_target()
        self.storage.delete("key")
        self.client.head_bucket.assert_called_once()
        self.client.get_object_lock_configuration.side_effect = s3_error("NotFound", 404)
        with self.assertRaises(ClientError):
            self.storage.validate_cleanup_target()

    def test_unknown_backend_is_rejected(self):
        with patch.object(settings, "STORAGE_BACKEND", "unrecognized"):
            with self.assertRaises(StorageSafetyError):
                get_storage()


class CleanupPolicyTestCase(unittest.TestCase):
    def test_error_classification_and_safe_messages(self):
        cases = [
            (ReadTimeoutError(endpoint_url="https://secret@example.test"), CleanupStatus.RETRY),
            (EndpointConnectionError(endpoint_url="https://secret@example.test"), CleanupStatus.RETRY),
            (TimeoutError("never-log-secret"), CleanupStatus.RETRY),
            (s3_error("ServiceUnavailable", 503), CleanupStatus.RETRY),
            (s3_error("SlowDown", 400), CleanupStatus.RETRY),
            (s3_error("Throttling", 429), CleanupStatus.RETRY),
            (s3_error("ThrottlingException", 400), CleanupStatus.RETRY),
            (s3_error("AccessDenied", 403), CleanupStatus.BLOCKED),
            (s3_error("NoSuchBucket", 404), CleanupStatus.BLOCKED),
            (s3_error("NotFound", 404), CleanupStatus.BLOCKED),
            (PermissionError("never-log-secret"), CleanupStatus.BLOCKED),
            (OSError(errno.EIO, "never-log-secret"), CleanupStatus.RETRY),
            (OSError(errno.ELOOP, "never-log-secret"), CleanupStatus.BLOCKED),
            (StorageSafetyError("target_mismatch"), CleanupStatus.BLOCKED),
            (RuntimeError("never-log-secret"), CleanupStatus.BLOCKED),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                outcome = classify_cleanup_error(error)
                self.assertEqual(outcome.status, expected)
                self.assertNotIn("secret", outcome.message)
                self.assertNotIn("https", outcome.message)

    def test_backoff_boundary_caps_exponent_before_overflow_and_jitter_is_80_to_100_percent(self):
        def upper(*_):
            return 1.0
        lower = Mock(return_value=0.8)
        self.assertEqual([cleanup_retry_delay(i, jitter=upper) for i in (0, 1, 2, 8, 9, 10**100)],
                         [30, 30, 60, 3600, 3600, 3600])
        self.assertEqual(cleanup_retry_delay(1, jitter=lower), 24)
        lower.assert_called_once_with(0.8, 1.0)

    def test_shutdown_before_poll_does_not_claim(self):
        stop, service = threading.Event(), Mock()
        stop.set()
        run_worker(service, stop)
        service.run_once.assert_not_called()

    def test_empty_poll_and_shutdown_and_failures_do_not_log_secrets(self):
        for error in (None, RuntimeError("never-log-secret")):
            stop, service = threading.Event(), Mock()

            def poll():
                stop.set()
                if error:
                    raise error
                return False

            service.run_once.side_effect = poll
            if error:
                with self.assertLogs("app.cleanup_worker", level="ERROR") as logs:
                    run_worker(service, stop)
                self.assertNotIn("never-log-secret", " ".join(logs.output))
            else:
                run_worker(service, stop)
            service.run_once.assert_called_once()

    def test_startup_rejects_non_postgres_and_insufficient_s3_lease(self):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=None)
        session.get_bind.return_value.dialect.name = "sqlite"
        with patch.multiple(settings, STORAGE_BACKEND="local", UPLOAD_DIR="test-root"):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
                validate_startup(lambda: session)
        session.get_bind.return_value.dialect.name = "postgresql"
        with patch.multiple(settings, STORAGE_BACKEND="s3", STORAGE_BUCKET="test",
                            STORAGE_ENDPOINT_URL="http://127.0.0.1:9000", CLEANUP_LEASE_SECONDS=1):
            with self.assertRaisesRegex(RuntimeError, "lease"):
                validate_startup(lambda: session)

    def test_startup_error_does_not_print_connection_credentials(self):
        with patch("app.cleanup_worker.signal.signal"), patch("app.cleanup_worker.create_engine", side_effect=RuntimeError("never-log-database-secret")), self.assertLogs(
            "app.cleanup_worker", level="ERROR",
        ) as logs, self.assertRaises(SystemExit) as exited:
            main()
        self.assertEqual(exited.exception.code, 1)
        self.assertNotIn("never-log-database-secret", " ".join(logs.output))
