from __future__ import annotations

import tempfile
import shutil
import errno
import os
import stat
import sys
from contextlib import contextmanager, ExitStack
from pathlib import Path
from typing import BinaryIO, ContextManager, Iterator, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings


class StorageSafetyError(ValueError):
    """A constant, credential-free code suitable for a blocked cleanup job."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _local_relative_path(location: str) -> tuple[Path, Path]:
    root = Path(settings.UPLOAD_DIR).resolve()
    path = Path(location).absolute()
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise StorageSafetyError("path_outside_root") from exc
    if not relative.parts or ".." in relative.parts:
        raise StorageSafetyError("invalid_local_path")
    return root, relative


@contextmanager
def _windows_directory_guards(path: Path):
    # Deny write/delete sharing on every ancestor, blocking both rename and
    # in-place reparse metadata changes between validation and unlink.
    if sys.platform != "win32":
        raise StorageSafetyError("windows_guard_unavailable")
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
    with ExitStack() as stack:
        for directory in [*reversed(path.parents), path]:
            # FILE_LIST_DIRECTORY participates in sharing checks; a metadata-
            # only handle (access=0) does not provide this exclusion.
            handle = create(str(directory), 1, 1, None, 3, 0x02200000, None)
            if handle == wintypes.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            stack.callback(close, handle)
            if os.lstat(directory).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise StorageSafetyError("symlink_not_allowed")
        yield


class ObjectStorage(Protocol):
    def save(self, key: str, content: bytes, content_type: str) -> str: ...
    def save_stream(self, key: str, stream: BinaryIO, content_type: str) -> str: ...
    def read(self, location: str) -> bytes: ...
    def size(self, location: str) -> int | None: ...
    def delete(self, location: str) -> None:
        """Delete one object idempotently; propagate permission, target and I/O errors."""
        ...

    def materialize(self, location: str, suffix: str) -> ContextManager[Path]: ...


class LocalStorage:
    def save(self, key: str, content: bytes, content_type: str) -> str:
        del content_type
        path = Path(settings.UPLOAD_DIR) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def save_stream(self, key: str, stream: BinaryIO, content_type: str) -> str:
        del content_type
        path = Path(settings.UPLOAD_DIR) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as destination:
            shutil.copyfileobj(stream, destination, length=1024 * 1024)
        return str(path)

    def read(self, location: str) -> bytes:
        return Path(location).read_bytes()

    def size(self, location: str) -> int | None:
        try:
            return Path(location).stat().st_size
        except OSError:
            return None

    def delete(self, location: str) -> None:
        root, relative = _local_relative_path(location)
        if sys.platform == "win32":
            # Opening the configured root/ancestors is outside the missing-entry
            # handler. An unavailable volume is not evidence of object absence.
            with _windows_directory_guards(root):
                try:
                    with _windows_directory_guards(root / relative.parent):
                        path = root / relative
                        if os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                            raise StorageSafetyError("symlink_not_allowed")
                        path.unlink()
                except FileNotFoundError as exc:
                    # Network-path errors can also map to FileNotFoundError.
                    if getattr(exc, "winerror", None) not in {2, 3}:
                        raise
        else:
            # dir_fd + O_NOFOLLOW closes the parent-symlink TOCTOU window.
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            with ExitStack() as stack:
                fd = os.open(root, flags)  # Root failures must propagate.
                stack.callback(os.close, fd)
                try:
                    for part in relative.parts[:-1]:
                        fd = os.open(part, flags, dir_fd=fd)
                        stack.callback(os.close, fd)
                    info = os.stat(relative.name, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        raise StorageSafetyError("symlink_not_allowed")
                    os.unlink(relative.name, dir_fd=fd)
                except FileNotFoundError as exc:
                    # Only a missing entry beneath an opened root is success.
                    if exc.errno != errno.ENOENT:
                        raise

    @contextmanager
    def materialize(self, location: str, suffix: str) -> Iterator[Path]:
        del suffix
        yield Path(location)


class S3Storage:
    def __init__(self, *, cleanup: bool = False):
        self.bucket = settings.STORAGE_BUCKET
        options = {}
        if cleanup:
            options["config"] = Config(
                connect_timeout=settings.CLEANUP_CONNECT_TIMEOUT_SECONDS,
                read_timeout=settings.CLEANUP_READ_TIMEOUT_SECONDS,
                retries={"total_max_attempts": 1, "mode": "standard"},
            )
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
            region_name=settings.STORAGE_REGION,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
            aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
            **options,
        )
        self._cleanup_target_validated = False

    def validate_cleanup_target(self) -> None:
        """Only unversioned, unlocked buckets are supported by this worker."""
        self.client.head_bucket(Bucket=self.bucket)
        versioning = self.client.get_bucket_versioning(Bucket=self.bucket)
        if versioning.get("Status") is not None:
            raise StorageSafetyError("versioning_unsupported")
        try:
            lock = self.client.get_object_lock_configuration(Bucket=self.bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in {"ObjectLockConfigurationNotFoundError", "NoSuchObjectLockConfiguration"}:
                raise
        else:
            if lock.get("ObjectLockConfiguration", {}).get("ObjectLockEnabled") == "Enabled":
                raise StorageSafetyError("object_lock_unsupported")
        self._cleanup_target_validated = True

    def save(self, key: str, content: bytes, content_type: str) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return key

    def save_stream(self, key: str, stream: BinaryIO, content_type: str) -> str:
        self.client.upload_fileobj(
            stream, self.bucket, key, ExtraArgs={"ContentType": content_type}
        )
        return key

    def read(self, location: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=location)["Body"].read()

    def size(self, location: str) -> int | None:
        try:
            metadata = self.client.head_object(Bucket=self.bucket, Key=location)
            return int(metadata["ContentLength"])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def delete(self, location: str) -> None:
        if not self._cleanup_target_validated:
            self.client.head_bucket(Bucket=self.bucket)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=location)
        except ClientError as exc:
            # A generic 404 can mean a missing bucket or wrong endpoint.
            if exc.response.get("Error", {}).get("Code") != "NoSuchKey":
                raise

    @contextmanager
    def materialize(self, location: str, suffix: str) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="slrms-object-") as temp_dir:
            path = Path(temp_dir) / f"document{suffix}"
            self.client.download_file(self.bucket, location, str(path))
            yield path


def get_storage(*, cleanup: bool = False) -> ObjectStorage:
    if settings.STORAGE_BACKEND.lower() == "s3":
        return S3Storage(cleanup=cleanup)
    if settings.STORAGE_BACKEND.lower() == "local":
        return LocalStorage()
    raise StorageSafetyError("unsupported_backend")
