from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager, Iterator, Protocol

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


class ObjectStorage(Protocol):
    def save(self, key: str, content: bytes, content_type: str) -> str: ...
    def read(self, location: str) -> bytes: ...
    def size(self, location: str) -> int | None: ...
    def delete(self, location: str) -> None: ...

    def materialize(self, location: str, suffix: str) -> ContextManager[Path]: ...


class LocalStorage:
    def save(self, key: str, content: bytes, content_type: str) -> str:
        del content_type
        path = Path(settings.UPLOAD_DIR) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def read(self, location: str) -> bytes:
        return Path(location).read_bytes()

    def size(self, location: str) -> int | None:
        try:
            return Path(location).stat().st_size
        except OSError:
            return None

    def delete(self, location: str) -> None:
        try:
            Path(location).unlink(missing_ok=True)
        except OSError:
            pass

    @contextmanager
    def materialize(self, location: str, suffix: str) -> Iterator[Path]:
        del suffix
        yield Path(location)


class S3Storage:
    def __init__(self):
        self.bucket = settings.STORAGE_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
            region_name=settings.STORAGE_REGION,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID,
            aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY,
        )

    def save(self, key: str, content: bytes, content_type: str) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
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
        self.client.delete_object(Bucket=self.bucket, Key=location)

    @contextmanager
    def materialize(self, location: str, suffix: str) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="slrms-object-") as temp_dir:
            path = Path(temp_dir) / f"document{suffix}"
            self.client.download_file(self.bucket, location, str(path))
            yield path


def get_storage() -> ObjectStorage:
    if settings.STORAGE_BACKEND.lower() == "s3":
        return S3Storage()
    return LocalStorage()
